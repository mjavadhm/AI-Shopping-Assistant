from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import json


from app.schemas.chat import ChatRequest, ChatResponse
from app.services.openai_service import simple_openai_gpt_request, simple_openai_gpt_request_with_tools
from app.llm.prompts import FIND_PRODUCT_PROMPTS, ROUTER_PROMPT,SCENARIO_TWO_PROMPTS, SCENARIO_THREE_PROMPTS
from app.db.session import get_db
from app.llm.tools.definitions import FIRST_SCENARIO_TOOLS
from app.llm.tools.handler import ToolHandler
from app.core.utils import parse_llm_response_to_number
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
            elif scenario == "SCENARIO_2_FEATURE_EXTRACTION":
                response = await scenario_two(request, db=db)
            elif scenario == "SCENARIO_3_SELLER_INFO":
                response = await scenario_three(request, db=db)
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
    user_message = request.messages[-1].content.strip()
    found_keys = await find_exact_product_name_service(user_message, db)
    return ChatResponse(base_random_keys=found_keys)

async def scenario_two(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    user_message = request.messages[-1].content.strip()
    found_keys = await find_exact_product_name_service(user_message, db)
    if found_keys:
        first_key = found_keys[0]
        product = await repository.get_product_by_random_key(db, first_key)
    
        message = f"user input:{user_message}\n\nproduct_feautures:{str(product.extra_features)}"
        system_prompt = SCENARIO_TWO_PROMPTS.get("main_prompt_step_2", "")

        llm_response = await simple_openai_gpt_request(
                message=message,
                systemprompt=system_prompt,
                model="gpt-4.1-mini",
                        
            )
        
        logger.info(f"llm response:{llm_response}")
        return ChatResponse(message=llm_response)

async def scenario_three(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    user_message = request.messages[-1].content.strip()
    
    found_keys = await find_exact_product_name_service(user_message, db)
    if not found_keys:
        raise HTTPException(status_code=404, detail="Product not found.")

    first_key = found_keys[0]
    product = await repository.get_product_by_random_key(db, first_key)

    if not product or not product.members:
        raise HTTPException(status_code=404, detail=f"No sellers found for product: {first_key}")
    member_keys = product.members
    logger.info(f"-> Member keys to fetch: {member_keys}")
    member_objects = await repository.get_members_by_keys(db, member_keys)

    if not member_objects:
        raise HTTPException(status_code=404, detail=f"Seller details could not be found for product: {first_key}")
    logger.info(f"-> Successfully fetched {len(member_objects)} Member objects.")
    
    logger.info("STEP 3: Fetching Shop details...")
    
    shop_ids = [member.shop_id for member in member_objects]
    logger.info(f"-> Shop IDs to fetch: {list(set(shop_ids))}")
    shops_with_details = await repository.get_shops_with_details_by_ids(db, list(set(shop_ids)))
    shop_details_map = {shop.id: shop for shop in shops_with_details}
    # logger.info(f"-> Successfully fetched details for {len(shop_details_map)} shops.")

    # logger.info("STEP 4: Combining all data to create the final context...")
    
    sellers_context = []
    for member in member_objects:
        shop_info = shop_details_map.get(member.shop_id)
        if shop_info and shop_info.city:
            sellers_context.append({
                "price": member.price,
                "city": shop_info.city.name,
                "shop_score": shop_info.score,
                "has_warranty": shop_info.has_warranty
            })
    # logger.info(f"-> Final sellers_context being sent to LLM: {json.dumps(sellers_context, ensure_ascii=False, indent=2)}")
    if not sellers_context:
         raise HTTPException(status_code=404, detail=f"Could not construct complete seller details for product: {first_key}")

    context_str = json.dumps(sellers_context, ensure_ascii=False, indent=2)
    context_str = f"total shops:{str(len(shop_details_map))}\n\n\n" + context_str
    final_prompt = SCENARIO_THREE_PROMPTS["final_prompt_template"].format(
        user_message=user_message,
        context_str=context_str
    )
    system_prompt = SCENARIO_THREE_PROMPTS["system_prompt"]
    logger.info(f"-> final_prompt: {final_prompt}")
    logger.info(f"-> system_prompt: {system_prompt}")
    llm_response = await simple_openai_gpt_request(
        message=final_prompt,
        systemprompt=system_prompt,
        model="gpt-4.1-mini",
    )
    logger.info(f"-> Raw response from LLM: {llm_response}")
    final_answer = parse_llm_response_to_number(llm_response)
    logger.info(f"-> Parsed final answer: {final_answer}")
    
    return ChatResponse(message=final_answer)
    

async def find_exact_product_name_service(user_message: str, db: AsyncSession) -> Optional[str]:
    system_prompt = FIND_PRODUCT_PROMPTS.get("main_prompt", "")
    tool_handler = ToolHandler(db=db)
    llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        message=user_message,
        systemprompt=system_prompt,
        model="gpt-5",
        tools=FIRST_SCENARIO_TOOLS
    )
    tools_answer = []
    for _ in range(5):
        if tool_calls:
            tools_answer = await tool_handler.handle_tool_call(tool_calls, tools_answer)
            
            llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
                message=user_message,
                systemprompt=system_prompt,
                model="gpt-4.1-mini",
                tools=FIRST_SCENARIO_TOOLS,
                tools_answer=tools_answer
            )
        else:
            break
    
    logger.info(f"llm_response: {llm_response}")
    p_name = llm_response.split('\n')[0]
    p_name = p_name.strip()
    logger.info(f"cleaned name:{p_name}")
    found_keys = await repository.search_product_by_name(db=db, product_name=p_name)
    logger.info(f"found_keys: {found_keys}")
    return found_keys