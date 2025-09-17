from sqlalchemy.ext.asyncio import AsyncSession


from app.schemas.chat import ChatRequest, ChatResponse
from app.services.openai_service import simple_openai_gpt_request, simple_openai_gpt_request_with_tools
from app.llm.prompts import SCENARIO_ONE_PROMPTS, ROUTER_PROMPT
from app.db.session import get_db
from app.llm.tools.definitions import FIRST_SCENARIO_TOOLS
from app.llm.tools.handler import ToolHandler
from app.db import repository
from app.core.logger import logger


async def check_scenario_one(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    """
    Check if the request matches Scenario One and process it accordingly.

    Args:
        request (ChatRequest): The incoming chat request.
    Returns:
        ChatResponse: The response for Scenario One or None if not matched.
    """
    try:
        last_message = request.messages[-1].content.strip()
        response = None

        # --- Scenario Zero: Sanity Checks ---
        if last_message == "ping":
            response = ChatResponse(message="pong")

        elif last_message.startswith("return base random key:"):
            key = last_message.replace("return base random key:", "").strip()
            response = ChatResponse(base_random_keys=[key])

        elif last_message.startswith("return member random key:"):
            key = last_message.replace("return member random key:", "").strip()
            response = ChatResponse(member_random_keys=[key])

        else:
            scenario = await classify_scenario(request)
            logger.info(f"CLASSIFIED SCENARIO: {scenario}")
            if scenario == "SCENARIO_1_DIRECT_SEARCH":
                response = await scenario_one(request, db=db)
            
        return response
    except Exception as e:
        logger.error(e,exc_info=True)




async def classify_scenario(request: ChatRequest) -> str:
    """
    Classifies the user's request into a specific scenario using the router prompt.
    """
    try:
        system_prompt = ROUTER_PROMPT.get("main_prompt", "")
        last_message = request.messages[-1].content.strip()

        llm_response = await simple_openai_gpt_request(
            message=last_message,
            systemprompt=system_prompt,
            model="gpt-4.1-mini",
                    
        )

        scenario = llm_response.strip()
        return scenario
    except Exception as e:
        logger.error(e,exc_info=True)


async def scenario_one(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    system_prompt = SCENARIO_ONE_PROMPTS.get("main_prompt", "")
    user_message = request.messages[-1].content.strip()
    tool_handler = ToolHandler(db=db)
    llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        message=user_message,
        systemprompt=system_prompt,
        model="gpt-4.1-mini",
        tools=FIRST_SCENARIO_TOOLS
    )
    tools_answer = []
    while True:
        if tool_calls:
            tools_answer = await tool_handler.handle_tool_call(tool_calls, tools_answer)
            
            llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
                message=user_message,
                systemprompt=system_prompt,
                model="gpt-4.1-mini",
                tools=FIRST_SCENARIO_TOOLS
            )
        else:
            break
    logger.info(f"llm_response: {llm_response}")
    found_keys = await repository.search_product_by_name(db=db, product_name=llm_response)
    logger.info(f"found_keys: {found_keys}")
    return ChatResponse(base_random_keys=found_keys)
