from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Tuple
import json

from app.schemas.chat import ChatRequest, ChatResponse
from app.core.logger import logger
from app.services.openai_service import simple_openai_gpt_request_with_tools
from app.llm.prompts import FIRST_AGENT_PROMPT, SELECT_BEST_MATCH_PROMPT
from app.llm.tools.definitions import EMBED_FIRST_AGENT_TOOLS, EMBED_FIRST_SCENARIO_TOOLS
from app.db import repository

# Import scenario handlers from their new modules
from .scenarios import (
    scenario_1_direct,
    scenario_2_feature,
    scenario_3_seller,
    scenario_4_conversational,
    scenario_5_comparison,
    scenario_6_image
)

# A dictionary to map scenario names to their handler functions
SCENARIO_HANDLERS = {
    "SCENARIO_1_DIRECT_SEARCH": scenario_1_direct.handle,
    "SCENARIO_2_FEATURE_EXTRACTION": scenario_2_feature.handle,
    "SCENARIO_3_SELLER_INFO": scenario_3_seller.handle,
    "SCENARIO_4_CONVERSATIONAL_SEARCH": scenario_4_conversational.handle,
    "SCENARIO_5_COMPARISON": scenario_5_comparison.handle,
    "SCENARIO_6_IMAGE_OBJECT_DETECTION": scenario_6_image.handle,
}

async def route_chat_request(request: ChatRequest, db: AsyncSession, http_request: Request) -> ChatResponse:
    """
    Main router for incoming chat requests.
    It determines the user's intent (scenario) and forwards the request
    to the appropriate handler.
    """
    last_message = request.messages[-1].content.strip()

    # --- Handle special cases before calling the LLM ---
    if any(msg.type == 'image' for msg in request.messages):
        http_request.state.scenario = "SCENARIO_6_IMAGE_OBJECT_DETECTION"
        return await SCENARIO_HANDLERS["SCENARIO_6_IMAGE_OBJECT_DETECTION"](request, db)

    if scenario_4_conversational.is_active_session(request.chat_id):
        http_request.state.scenario = "SCENARIO_4_CONVERSATIONAL_SEARCH"
        return await SCENARIO_HANDLERS["SCENARIO_4_CONVERSATIONAL_SEARCH"](request, db)

    # --- Classify the scenario using the LLM ---
    scenario, possible_product_name = await _classify_scenario_and_extract_product(request)
    logger.info(f"CLASSIFIED SCENARIO: {scenario}, possible_product_name: {possible_product_name}")
    http_request.state.scenario = scenario

    # --- Find the product if required by the scenario ---
    found_key = None
    if scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_2_FEATURE_EXTRACTION", "SCENARIO_3_SELLER_INFO"]:
        found_key = await _find_exact_product_key(last_message, possible_product_name, db)
        if not found_key:
            raise HTTPException(status_code=404, detail="No products found matching the keywords.")

    # --- Route to the appropriate handler ---
    handler = SCENARIO_HANDLERS.get(scenario)
    if handler:
        if scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_2_FEATURE_EXTRACTION", "SCENARIO_3_SELLER_INFO"]:
            return await handler(request, db, found_key)
        else:
            return await handler(request, db)
    else:
        logger.warning(f"No handler found for scenario: {scenario}. Sending default response.")
        return ChatResponse(message="I'm sorry, I didn't understand your request. Could you please try again?")


async def _classify_scenario_and_extract_product(request: ChatRequest) -> Tuple[str, str]:
    """
    Classifies the user's intent into a scenario and extracts the key product name.
    """
    system_prompt = FIRST_AGENT_PROMPT.get("main_prompt", "")
    last_message = request.messages[-1].content.strip()

    try:
        _, tool_calls = await simple_openai_gpt_request_with_tools(
            message=last_message,
            systemprompt=system_prompt,
            model="gpt-4.1-mini",
            tools=EMBED_FIRST_AGENT_TOOLS
        )
        scenario = "UNCATEGORIZED"
        product_name = ""
        if not tool_calls:
            logger.warning("No tool calls returned from the model.")
            return scenario, product_name
        for tool_call in tool_calls:
            parsed_args = json.loads(tool_call.function.arguments)
            if tool_call.function.name == "classify_user_request":
                scenario = parsed_args.get("scenario", "UNCATEGORIZED")
            elif tool_call.function.name == "extract_search":
                product_name = parsed_args.get("product_name", "")
        return scenario, product_name
    except Exception as e:
        logger.error(f"Error in scenario classification: {e}", exc_info=True)
        return "UNCATEGORIZED", ""

async def _find_exact_product_key(user_message: str, possible_product_name: str, db: AsyncSession) -> str | None:
    """
    Finds the single most accurate product key by first searching for candidates
    in the database and then using an LLM to select the best match.
    This function replicates the logic from the original `find_exact_product_name_service`.
    """
    logger.info(f"Initiating exact product search for: '{possible_product_name}'")

    # Initial candidate search
    if possible_product_name:
        product_names = await repository.find_similar_products(
            db=db,
            product_name=possible_product_name,
        )
    else:
        product_names = "use function to search"

    # Prepare prompt for LLM to select the best match
    system_prompt = SELECT_BEST_MATCH_PROMPT.get("new_main_prompt_template_embed", "").format(
        user_query=user_message,
        search_results_str=str(product_names)
    )

    llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        message="",
        systemprompt=system_prompt,
        model="gpt-4.1-mini",
        tools=EMBED_FIRST_SCENARIO_TOOLS
    )

    # Iteratively handle tool calls if the LLM needs to refine the search
    tools_answer = []
    for _ in range(5):  # Limit iterations to prevent infinite loops
        if not tool_calls:
            break

        for tool_call in tool_calls:
            function_arguments = tool_call.function.arguments
            function_name = tool_call.function.name
            parsed_arguments = json.loads(function_arguments)

            logger.info(f"LLM tool call: {function_name} with args: {function_arguments}")
            
            # This logic assumes the tool is for searching, adjust if other tools are used
            new_possible_name = parsed_arguments.get("product_name")
            new_product_names = await repository.find_similar_products(db, new_possible_name)
            
            tools_answer.append({"role": "assistant", "tool_calls": [{"id": tool_call.id, "type": "function", "function": {"name": function_name, "arguments": function_arguments}}]})
            tools_answer.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(new_product_names)})

        # Call the LLM again with the tool's output
        llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
            message=user_message,
            systemprompt=system_prompt,
            model="gpt-4.1-mini",
            tools=EMBED_FIRST_SCENARIO_TOOLS,
            tools_answer=tools_answer
        )

    if not llm_response:
        logger.warning("LLM did not provide a final response for product selection.")
        return None

    found_key = llm_response.strip().split('\n')[0]
    logger.info(f"LLM selected final product key: {found_key}")
    return found_key