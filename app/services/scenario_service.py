import asyncio
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Tuple ,Dict
import json
# import aiohttp
import json

from app.schemas.state import Scenario4State
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.openai_service import simple_openai_gpt_request, simple_openai_gpt_request_with_tools, analyze_image
from app.llm.prompts import (FIND_PRODUCT_PROMPTS, FIRST_AGENT_PROMPT, OLD_FIND_PRODUCT_PROMPTS,
    ROUTER_PROMPT, SCENARIO_FIVE_PROMPTS, SCENARIO_FOUR_PROMPTS, SCENARIO_THREE_PROMPTS, SCENARIO_SIX_PROMPTS,
    SCENARIO_TWO_PROMPTS, SELECT_BEST_MATCH_PROMPT)
from app.db.session import get_db
from app.db.session import AsyncSessionLocal
from app.llm.tools.definitions import (EMBED_FIRST_AGENT_TOOLS, EMBED_FIRST_SCENARIO_TOOLS,
    FIRST_AGENT_TOOLS, FIRST_SCENARIO_TOOLS, OLD_FIRST_SCENARIO_TOOLS)
from app.llm.tools.handler import ToolHandler
from app.core.http_client import post_async_request
from app.core.utils import parse_llm_response_to_number
from app.db import repository
from app.core.logger import logger

scenario_4_sessions: Dict[str, Scenario4State] = {}

async def check_scenario_one(request: ChatRequest, db: AsyncSession, http_request: Request) -> ChatResponse:
    """
    Check if the request matches Scenario One and process it accordingly.

    Args:
        request (ChatRequest): The incoming chat request.
    Returns:
        ChatResponse: The response for Scenario One or None if not matched.
    """
    try:
        response = None
        scenario = "SANITY_CHECK"
        chat_id = request.chat_id
        if any(msg.type == 'image' for msg in request.messages):
            http_request.state.scenario = "SCENARIO_6_IMAGE_OBJECT_DETECTION"
            return await scenario_six(request)
        last_message = request.messages[-1].content.strip()
        session = scenario_4_sessions.get(chat_id)
        # --- Scenario Zero: Sanity Checks ---
        if last_message == "ping":
            response = ChatResponse(message="pong")

        elif last_message.startswith("return base random key:"):
            key = last_message.replace("return base random key:", "").strip()
            response = ChatResponse(base_random_keys=[key])

        elif last_message.startswith("return member random key:"):
            key = last_message.replace("return member random key:", "").strip()
            response = ChatResponse(member_random_keys=[key])
        
        elif session:
            scenario = "SCENARIO_4_CONVERSATIONAL_SEARCH"
            response = await scenario_four_in_memory(request, db)

        else:
            found_key = None
            #with full text search
            # scenario, essential_keywords, descriptive_keywords = await classify_scenario(request)
            scenario, product_name = await classify_scenario_for_embed(request)
            logger.info(f"CLASSIFIED SCENARIO: {scenario}, product_name: {product_name}")
            if scenario not in  ["SCENARIO_5_COMPARISON","SCENARIO_4_CONVERSATIONAL_SEARCH"]:
                found_key = await find_exact_product_name_service(user_message = request.messages[-1].content.strip(), db=db, possible_product_name=product_name)
            if not found_key and scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_2_FEATURE_EXTRACTION", "SCENARIO_3_SELLER_INFO"]:
                raise HTTPException(status_code=404, detail="No products found matching the keywords.")
            # return ChatResponse(base_random_keys=[found_key]) 
            #------------------------------------------
            #with keyword simple
            # scenario = await old_classify_scenario(request)
            if scenario:
                http_request.state.scenario = scenario
            logger.info(f"CLASSIFIED SCENARIO: {scenario}")
            # if scenario not in  ["SCENARIO_5_COMPARISON","SCENARIO_4_CONVERSATIONAL_SEARCH"]:
                
            #     found_key = await old_find_exact_product_name_service(user_message = request.messages[-1].content.strip(), db=db)
            #     logger.info(f"found_key: {found_key}")
            #-----------------------------------------------------
            #with embed
            #---------------------------------------------
            # keywords = ''
            # scenario, product_name = await classify_scenario_for_embed(request)
            # logger.info(f"CLASSIFIED SCENARIO: {scenario}, product_name: {product_name}")
            if scenario == "SCENARIO_4_CONVERSATIONAL_SEARCH":
                response = await scenario_four_in_memory(request,db)
            # if scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_2_FEATURE_EXTRACTION", "SCENARIO_3_SELLER_INFO"]:
                # found_key = await find_exact_product_name_service_and_embed(user_message = request.messages[-1].content.strip(), possible_product_name=product_name)
            elif not found_key and scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_2_FEATURE_EXTRACTION", "SCENARIO_3_SELLER_INFO"]:
                    raise HTTPException(status_code=404, detail="No products found matching the keywords.")
            
            
            # return ChatResponse(base_random_keys=[found_key])
            if scenario == "SCENARIO_1_DIRECT_SEARCH":
                return ChatResponse(base_random_keys=[found_key]) 
                # response = await scenario_one(request, db=db, essential_keywords=essential_keywords, descriptive_keywords=descriptive_keywords)
            elif scenario == "SCENARIO_2_FEATURE_EXTRACTION":
                response = await scenario_two(request, db=db, found_key=found_key)
            elif scenario == "SCENARIO_3_SELLER_INFO":
                response = await scenario_three(request, db=db, found_key=found_key)
            elif scenario == "SCENARIO_5_COMPARISON":
                response = await scenario_five(request, db=db)
        return response
    except Exception as e:
        logger.error(e,exc_info=True)


async def classify_scenario_for_embed(request: ChatRequest) -> Tuple[str, str]:
    """
    Classifies the user's request into a scenario and extracts keywords using tool calls.
    """
    try:
        system_prompt = FIRST_AGENT_PROMPT.get("main_prompt", "")
        last_message = request.messages[-1].content.strip()

        response, tool_calls = await simple_openai_gpt_request_with_tools(
            message=last_message,
            systemprompt=system_prompt,
            model="gpt-4.1-mini",
            tools=EMBED_FIRST_AGENT_TOOLS
        )

        scenario = "UNCATEGORIZED"
        product_name = ""
        logger.info(response)
        if not tool_calls:
            logger.warning("No tool calls returned from the model.")
            return scenario, product_name

        for tool_call in tool_calls:
            logger.info(f"Processing tool call: {tool_call.function.name}")
            try:
                parsed_args = json.loads(tool_call.function.arguments)
                if tool_call.function.name == "classify_user_request":
                    scenario = parsed_args.get("scenario", "UNCATEGORIZED")
                elif tool_call.function.name == "extract_search":
                    product_name = parsed_args.get("product_name", [])

            except json.JSONDecodeError:
                logger.error(f"Failed to parse arguments for tool {tool_call.function.name}")

        return scenario, product_name
        
    except Exception as e:
        logger.error(e, exc_info=True)
        return "UNCATEGORIZED", ""




async def classify_scenario(request: ChatRequest) -> Tuple[str, List[str], List[str]]:
    """
    Classifies the user's request into a scenario and extracts keywords using tool calls.
    """
    try:
        system_prompt = FIRST_AGENT_PROMPT.get("main_prompt", "")
        last_message = request.messages[-1].content.strip()

        _, tool_calls = await simple_openai_gpt_request_with_tools(
            message=last_message,
            systemprompt=system_prompt,
            model="gpt-4.1-mini",
            tools=FIRST_AGENT_TOOLS
        )

        # --- مقادیر پیش‌فرض برای جلوگیری از خطا ---
        scenario = "UNCATEGORIZED"
        essential_keywords = []
        descriptive_keywords = []

        if not tool_calls:
            logger.warning("No tool calls returned from the model.")
            return scenario, essential_keywords, descriptive_keywords

        for tool_call in tool_calls:
            logger.info(f"Processing tool call: {tool_call.function.name}")
            try:
                parsed_args = json.loads(tool_call.function.arguments)
                if tool_call.function.name == "classify_user_request":
                    scenario = parsed_args.get("scenario", "UNCATEGORIZED")
                elif tool_call.function.name == "extract_search_keywords":
                    essential_keywords = parsed_args.get("essential_keywords", [])
                    descriptive_keywords = parsed_args.get("descriptive_keywords", [])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse arguments for tool {tool_call.function.name}")

        return scenario, essential_keywords, descriptive_keywords
        
    except Exception as e:
        logger.error(e, exc_info=True)
        return "UNCATEGORIZED", [], []


async def old_classify_scenario(request: ChatRequest) -> str:
    """
    Classifies the user's request into a specific scenario using the router prompt.
    """
    try:
        system_prompt = ROUTER_PROMPT.get("main_prompt", "")
        last_message = request.messages[-1].content.strip()

        llm_response = await simple_openai_gpt_request(
            message=f"user_query: {last_message}",
            systemprompt=system_prompt,
            model="gpt-4.1-mini",
                    
        )

        scenario = llm_response.strip()
        return scenario
    except Exception as e:
        logger.error(e,exc_info=True)


# async def scenario_one(request: ChatRequest, db: AsyncSession) -> ChatResponse:
#     user_message = request.messages[-1].content.strip()
#     found_keys = await find_exact_product_name_service(user_message, db)
#     return ChatResponse(base_random_keys=found_keys)

async def scenario_two(request: ChatRequest, db: AsyncSession, found_key) -> ChatResponse:
    user_message = request.messages[-1].content.strip()
    logger.info(f"found_key in scenario two:{found_key}")
    product = await repository.get_product_by_random_key(db, found_key)
    
    message = f"user input:{user_message}\n\nproduct_feautures:{str(product.extra_features)}"
    system_prompt = SCENARIO_TWO_PROMPTS.get("main_prompt_step_2", "")

    llm_response = await simple_openai_gpt_request(
                message=message,
                systemprompt=system_prompt,
                model="gpt-4.1",
                        
            )
        
    logger.info(f"llm response:{llm_response}")
    return ChatResponse(message=llm_response)


async def get_sellers_context(db, random_key):
    product = await repository.get_product_by_random_key(db, random_key)

    if not product or not product.members:
        raise HTTPException(status_code=404, detail=f"No sellers found for product: {random_key}")

    member_keys = product.members
    member_objects = await repository.get_members_by_keys(db, member_keys)

    if not member_objects:
        raise HTTPException(status_code=404, detail=f"Seller details could not be found for product: {random_key}")

    shop_ids = [member.shop_id for member in member_objects]
    shops_with_details = await repository.get_shops_with_details_by_ids(db, list(set(shop_ids)))
    shop_details_map = {shop.id: shop for shop in shops_with_details}

    member_objects = await repository.get_members_by_keys(db, member_keys)

    if not member_objects:
        raise HTTPException(status_code=404, detail=f"Seller details could not be found for product: {random_key}")

    shop_ids = [member.shop_id for member in member_objects]
    shops_with_details = await repository.get_shops_with_details_by_ids(db, list(set(shop_ids)))
    shop_details_map = {shop.id: shop for shop in shops_with_details}

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
    return sellers_context


async def scenario_three(request: ChatRequest, db: AsyncSession, found_key) -> ChatResponse:
    user_message = request.messages[-1].content.strip()

    product = await repository.get_product_by_random_key(db, found_key)

    if not product or not product.members:
        raise HTTPException(status_code=404, detail=f"No sellers found for product: {found_key}")

    member_keys = product.members
    member_objects = await repository.get_members_by_keys(db, member_keys)

    if not member_objects:
        raise HTTPException(status_code=404, detail=f"Seller details could not be found for product: {found_key}")

    shop_ids = [member.shop_id for member in member_objects]
    shops_with_details = await repository.get_shops_with_details_by_ids(db, list(set(shop_ids)))
    shop_details_map = {shop.id: shop for shop in shops_with_details}

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

    if not sellers_context:
         raise HTTPException(status_code=404, detail=f"Could not construct complete seller details for product: {found_key}")

    context_str = json.dumps(sellers_context, ensure_ascii=False, indent=2)

    prompt_template = SCENARIO_THREE_PROMPTS["calculate_prompt"]

    code_generation_prompt = prompt_template.format(
        user_message=user_message,
        context_str=context_str
    )
    logger.info(f"-> context_str:\n{context_str}")

    llm_response_code = await simple_openai_gpt_request(
        message='',
        systemprompt=code_generation_prompt,
        model="gpt-4.1",
    )

    if "```python" in llm_response_code:
        llm_response_code = llm_response_code.split("```python")[1].split("```")[0].strip()

    logger.info(f"-> Generated Python code from LLM:\n{llm_response_code}")

    final_answer = ""
    try:

        local_scope = {}
        exec(llm_response_code, globals(), local_scope)

        calculator_func = local_scope.get('calculate')

        if callable(calculator_func):
    
            result = calculator_func(sellers_context)
            final_answer = str(result)
            logger.info(f"-> Calculated result from dynamic code: {final_answer}")
        else:
            logger.error("-> 'calculate' function not found or not callable in LLM response.")
            final_answer = llm_response_code
            raise HTTPException(status_code=500, detail="Internal error in processing the request.(calculate function error)")

    except Exception as e:
        logger.error(f"-> Error executing generated code: {e}", exc_info=True)

    return ChatResponse(message=final_answer)


# async def scenario_three(request: ChatRequest, db: AsyncSession, found_key) -> ChatResponse:
#     user_message = request.messages[-1].content.strip()
    
#     product = await repository.get_product_by_random_key(db, found_key)

#     if not product or not product.members:
#         raise HTTPException(status_code=404, detail=f"No sellers found for product: {found_key}")
#     member_keys = product.members
#     logger.info(f"-> Member keys to fetch: {member_keys}")
#     member_objects = await repository.get_members_by_keys(db, member_keys)

#     if not member_objects:
#         raise HTTPException(status_code=404, detail=f"Seller details could not be found for product: {found_key}")
#     logger.info(f"-> Successfully fetched {len(member_objects)} Member objects.")
    
#     logger.info("STEP 3: Fetching Shop details...")
    
#     shop_ids = [member.shop_id for member in member_objects]
#     logger.info(f"-> Shop IDs to fetch: {list(set(shop_ids))}")
#     shops_with_details = await repository.get_shops_with_details_by_ids(db, list(set(shop_ids)))
#     shop_details_map = {shop.id: shop for shop in shops_with_details}
#     # logger.info(f"-> Successfully fetched details for {len(shop_details_map)} shops.")

#     # logger.info("STEP 4: Combining all data to create the final context...")
    
#     sellers_context = []
#     for member in member_objects:
#         shop_info = shop_details_map.get(member.shop_id)
#         if shop_info and shop_info.city:
#             sellers_context.append({
#                 "price": member.price,
#                 "city": shop_info.city.name,
#                 "shop_score": shop_info.score,
#                 "has_warranty": shop_info.has_warranty
#             })
#     # logger.info(f"-> Final sellers_context being sent to LLM: {json.dumps(sellers_context, ensure_ascii=False, indent=2)}")
#     if not sellers_context:
#          raise HTTPException(status_code=404, detail=f"Could not construct complete seller details for product: {found_key}")

#     context_str = json.dumps(sellers_context, ensure_ascii=False, indent=2)
#     context_str = f"total shops:{str(len(shop_details_map))}\n\n\n" + context_str
#     final_prompt = SCENARIO_THREE_PROMPTS["final_prompt_template"].format(
#         user_message=user_message,
#         context_str=context_str
#     )
#     system_prompt = SCENARIO_THREE_PROMPTS["system_prompt"]
#     logger.info(f"-> final_prompt: {final_prompt}")
#     logger.info(f"-> system_prompt: {system_prompt}")
#     llm_response = await simple_openai_gpt_request(
#         message='',
#         systemprompt=final_prompt,
#         model="gpt-5-mini",
#     )
#     logger.info(f"-> Raw response from LLM: {llm_response}")
#     final_answer = parse_llm_response_to_number(llm_response)
#     logger.info(f"-> Parsed final answer: {final_answer}")
    
#     return ChatResponse(message=final_answer)
    
    
    
async def scenario_four_in_memory(request: ChatRequest, db) -> ChatResponse:
    user_message = request.messages[-1].content.strip()
    chat_id = request.chat_id

    # 1. Get chat history from memory
    response =  "سلام اگه امکانش هست کامل توضیح بدید چی میخواید تا بتونم بهتر کمکتون کنم\nدرباره فروشنده گارانتی یا قیمت"
    session = scenario_4_sessions.get(chat_id)
    if len(session.chat_history) > 4:
        response, session, is_ok = await scenario_4_emergancy_state(user_message, db, session)
        return ChatResponse(message=response)
    if not session:
        session = Scenario4State()
        scenario_4_sessions[chat_id] = session
    
    session.chat_history.append({"role": "user", "content": user_message})

    if session.state == 1 or not session.state:
        response, session = await scenario_4_state_1(user_message, session)

    elif session.state == 2:
        response, session = await scenario_4_state_2(user_message, db, session)
    elif session.state == 3:
        response, session, is_done = await scenario_4_state_3(user_message, db, session)
        if is_done:
            return ChatResponse(member_random_keys=response)
        
    session.chat_history.append({"role": "assistant", "content": response})
    scenario_4_sessions[chat_id] = session
    
    
    return ChatResponse(message=response)
    
    
async def scenario_4_state_1(user_message, session):
    history = session.chat_history
    llm_response = await simple_openai_gpt_request(
        message=user_message,  # Send only the latest message
        systemprompt=SCENARIO_FOUR_PROMPTS["system_prompt"],
        model="gpt-4.1-mini",
        chat_history=history  # Pass the list of previous messages directly
    )

    # 3. Process response and update history in memory
    response_text = llm_response.strip()
    session.state = 2

    return response_text, session

async def scenario_4_state_2(user_message, db, session: Scenario4State):

    history = session.chat_history

    system_prompt_extract = SCENARIO_FOUR_PROMPTS["extract_info"].format(
        chat_history=str(history)
    )
    
    
    llm_response_str = await simple_openai_gpt_request(
        message="",
        systemprompt=system_prompt_extract,
        model="gpt-4.1-mini", 
    )

    logger.info(f"\n{llm_response_str}")
    try:
        
        json_str = llm_response_str.split("```json")[1].split("```")[0].strip()
        filters_json = json.loads(json_str)
        
        
        products_with_sellers = await repository.find_products_with_aggregated_sellers(db, filters_json)
        session.products_with_sellers = products_with_sellers
        logger.info(f"products_with_sellers:\n{str(products_with_sellers)}")
    except (json.JSONDecodeError, IndexError) as e:
        
        print(f"Error parsing LLM response: {e}")
        
        final_message = "متاسفانه در حال حاضر امکان پردازش درخواست شما وجود ندارد. لطفاً کمی دیگر دوباره تلاش کنید."
        
        return final_message, session

    
    session.filters_json = filters_json
    navigator_prompt = SCENARIO_FOUR_PROMPTS["state_2_path"]
    input_for_navigator_prompt = {}
    

    # PATH A
    if 1 <= len(products_with_sellers) :
        logger.info("Path A: Success, 1-5 results found.")
        input_for_navigator_prompt = {
            "action_mode": "HANDLE_SUCCESSFUL_RESULTS",
            "search_results": products_with_sellers, # فرض می‌کنیم فرمت این لیست مناسب است
            "last_search_parameters": filters_json,
            "chat_history": str(history)
        }
        session.state = 3

    # PATH B
    elif len(products_with_sellers) == 0:
        logger.info("Path B, Attempt 1: No results found. Generating recovery query.")

        
        original_query = filters_json.get("search_query", "")
        
        input_for_recovery_query = {
            "action_mode": "GENERATE_RECOVERY_QUERY",
            "search_results": [],
            "last_search_parameters": {
                "search_query": original_query 
            },
            "chat_history": str(history)
        }
        
        recovery_response_str = await simple_openai_gpt_request(
            message=json.dumps(input_for_recovery_query),
            systemprompt=navigator_prompt,
            model="gpt-4.1-mini",
        )
        recovery_response_json = json.loads(recovery_response_str)
        
        new_search_query = recovery_response_json.get("new_search_query")
        
        if new_search_query:
            logger.info(f"Retrying search with new query: '{new_search_query}'")
            

            updated_filters_for_db = {
                "search_query": new_search_query,
                "structured_filters": filters_json.get("structured_filters", {})
            }
            
            second_attempt_products = await repository.find_products_with_aggregated_sellers(db, updated_filters_for_db)
            session.products_with_sellers = second_attempt_products
            if 1 <= len(second_attempt_products):
                logger.info("Path B, Recovery Success: Found results on second attempt.")
                input_for_navigator_prompt = {
                    "action_mode": "HANDLE_SUCCESSFUL_RESULTS",
                    "search_results": second_attempt_products,
                    "last_search_parameters": updated_filters_for_db,
                    "chat_history": str(history)
                }
                session.state = 3
            else:
                logger.info("Path B, Attempt 2: Still no results. Generating clarification message.")
                input_for_navigator_prompt = {
                    "action_mode": "GENERATE_CLARIFICATION_MESSAGE",
                    "search_results": [],
                    "last_search_parameters": updated_filters_for_db,
                    "chat_history": str(history)
                }
        else:
            logger.warning("LLM failed to generate a recovery query.")
            input_for_navigator_prompt = {
                "action_mode": "GENERATE_CLARIFICATION_MESSAGE",
                "search_results": [],
                "last_search_parameters": filters_json,
                "chat_history": str(history)
            }
            
    else: # len(products_with_sellers) > 5
        logger.info("Path C: Too many results found. Asking user to narrow down.")

        final_message = "تعداد زیادی محصول با این مشخصات پیدا شد! لطفاً مشخصات دقیق‌تری مثل بازه قیمت یا رنگ مورد نظرتان را بگویید تا بتوانم بهتر کمکتان کنم."
        history.append({"role": "assistant", "content": final_message})
        
        return final_message, session

    final_response_str = await simple_openai_gpt_request(
        message=json.dumps(input_for_navigator_prompt),
        systemprompt=navigator_prompt,
        model="gpt-4.1-mini",
    )
    
    
    final_response_json = json.loads(final_response_str)
    final_message = final_response_json.get("message", "متاسفانه مشکلی پیش آمده.")

    history.append({"role": "assistant", "content": final_message})
    
    return final_message, session
    
    
async def scenario_4_state_3(user_message, db, session: Scenario4State):
    history = session.chat_history
    products_with_sellers = session.products_with_sellers
    filters_json = session.filters_json
    logger.info(f"products_with_sellers in state 3:\n{str(products_with_sellers)}")
    if not products_with_sellers:
        raise HTTPException(status_code=404, detail="No products found in previous steps.")
    
    system_prompt = SCENARIO_FOUR_PROMPTS["final_recommendation"]
    input_for_selection = {
        "user_response": user_message,
        "product_options": str(products_with_sellers), # Correct key and data
        "chat_history": str(history)
    }
    llm_response = await simple_openai_gpt_request(
        message=json.dumps(input_for_selection),
        systemprompt=system_prompt,
        model="gpt-4.1",
    )
    logger.info(f"llm_response in state 3:\n{str(llm_response)}")

    json_from_llm = parse_llm_json_response(llm_response)

    
    final_user_message = json_from_llm.get("selected_member_key")
    if not final_user_message:
        session.state = 2
        response, session = await scenario_4_state_2(user_message, db, session)
        return response, session, False

    member_key = final_user_message

    
    return [member_key], session, True

async def scenario_4_state_4(user_message, db, session: Scenario4State):
    # This state can be implemented if needed for further interactions
    pass

async def scenario_4_emergancy_state(user_message, db, session):
    history = session.chat_history
    products_with_sellers = session.products_with_sellers
    filters_json = session.filters_json
    logger.info(f"products_with_sellers in state 3:\n{str(products_with_sellers)}")
    if not products_with_sellers:
        raise HTTPException(status_code=404, detail="No products found in previous steps.")
    
    system_prompt = SCENARIO_FOUR_PROMPTS["emergancy_response"]
    input_for_selection = {
        "user_response": user_message,
        "product_options": str(products_with_sellers), # Correct key and data
        "chat_history": str(history)
    }
    llm_response = await simple_openai_gpt_request(
        message=json.dumps(input_for_selection),
        systemprompt=system_prompt,
        model="gpt-4.1",
    )
    logger.info(f"llm_response in state 3:\n{str(llm_response)}")

    json_from_llm = parse_llm_json_response(llm_response)

    
    final_user_message = json_from_llm.get("selected_member_key")


    member_key = final_user_message

    
    return [member_key], session, True


def parse_llm_json_response(response_str: str) -> dict:
    """
    A robust function to parse JSON from an LLM response,
    handling both raw JSON and JSON wrapped in markdown code fences.
    """
    try:
        # First, check if the response is wrapped in markdown fences
        if "```json" in response_str:
            # Extract the content between the fences
            json_part = response_str.split("```json")[1].split("```")[0].strip()
            return json.loads(json_part)
        else:
            # If no fences, assume the whole string is the JSON
            return json.loads(response_str.strip())
    except (json.JSONDecodeError, IndexError) as e:
        print(f"Error parsing JSON from LLM response: {e}")
        # Return an empty dict or raise an exception as needed
        return {}


async def scenario_five(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    user_message = request.messages[-1].content.strip()
    logger.info("Initiating Scenario 5: Product Comparison.")

    product_data = await find_two_product(user_message, AsyncSessionLocal)

    if product_data is None:
        logger.error("Failed to retrieve data for one or both products in comparison.")
        raise HTTPException(status_code=500, detail="Could not process the comparison due to an internal error.")

    first_product, second_product, code_to_get_info = product_data
    logger.info(f"code_to_get_info type: {type(code_to_get_info)}\ncode_to_get_info:\n{code_to_get_info}")
    
    logger.info(f"First product key: {first_product.random_key if first_product else 'None'}")
    product_1_details = await get_product_detail(db, first_product, code_to_get_info)
    logger.info(f"product_1_details: {product_1_details}")
    
    logger.info(f"Second product key: {second_product.random_key if second_product else 'None'}")
    product_2_details = await get_product_detail(db, second_product, code_to_get_info)
    logger.info(f"product_2_details: {product_2_details}")

    comparison_system_prompt = SCENARIO_FIVE_PROMPTS.get("comparison_prompt").format(
        user_query=user_message,
        product_1_details=product_1_details,
        product_2_details=product_2_details,
        product_1_key = first_product.random_key,
        product_2_key = second_product.random_key
    )

    final_response_text = await simple_openai_gpt_request(
        message="",
        systemprompt=comparison_system_prompt,
        model="gpt-4.1-mini"
    )
    
    try:
        json_part_str = final_response_text.split("```")[1].replace("json\n", "").strip()
        text_explanation = final_response_text.split("```")[-1].strip()

        response_json = json.loads(json_part_str)
        winning_name = response_json.get("winning_product_name")

        winning_key = response_json.get("random_key")
        
        logger.info(f"LLM selected winner: '{winning_name}' with key: {winning_key}")

        return ChatResponse(
            message=text_explanation,
            base_random_keys=[winning_key] if winning_key else []
        )

    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Could not parse LLM response for comparison: {e}")
        # اگر LLM فرمت را رعایت نکرد، کل متنش را به عنوان پاسخ برمی‌گردانیم
        return ChatResponse(message=final_response_text)


async def scenario_six(request: ChatRequest) -> ChatResponse:
    """
    Handles Scenario Six: Object detection in an image.
    """
    logger.info("Initiating Scenario 6: Image Object Detection.")
    
    text_message = ""
    base64_image = ""

    # Extract text and image content from messages
    for message in request.messages:
        if message.type == "text":
            text_message = message.content
        elif message.type == "image":
            base64_image = message.content

    if not base64_image:
        raise HTTPException(status_code=400, detail="Image content not found in the request.")

    # Get the prompt for object detection
    prompt = SCENARIO_SIX_PROMPTS.get("main_prompt", "Identify the main object in the image.")

    # Call the vision model service
    logger.info(f"{base64_image}\n{text_message}")
    object_name = await analyze_image(
        user_message=text_message,
        base64_image=base64_image,
        prompt=prompt
    )

    return ChatResponse(message=object_name)


async def get_product_detail(db, product, code_to_get_info):
    sellers_context = await get_sellers_context(db, product.random_key)
    logger.info(f"product id:{product.random_key}\ncontext:{str(sellers_context)}\n\ncode_to_get_info:{code_to_get_info}")
    try:
        logger.info(f"code_to_get_info type: {type(code_to_get_info)}\ncode_to_get_info:\n{code_to_get_info}")
        local_scope = {}
        exec(code_to_get_info, globals(), local_scope)

        calculator_func = local_scope.get('calculate')
        

        if callable(calculator_func):
    
            result = calculator_func(sellers_context)
            if result == None:
                final_answer = None
            else:
                final_answer = str(result)
            logger.info(f"-> Calculated result from dynamic code: {final_answer}")
        else:
            logger.error("-> 'calculate' function not found or not callable in LLM response.")
            final_answer = code_to_get_info
            raise HTTPException(status_code=500, detail="Internal error in processing the request.(calculate function error)")

    except Exception as e:
        logger.error(f"-> Error executing generated code: {e}", exc_info=True)
        
    if final_answer:
        product_details = json.dumps({
            "random_key(id)": product.random_key,
            "persian_name": product.persian_name,
            "features": product.extra_features or {},
            "sellers_info": final_answer
        }, ensure_ascii=False, indent=2)
        
    else:
        product_details = json.dumps({
            "random_key(id)": product.random_key,
            "persian_name": product.persian_name,
            "features": product.extra_features or {}
        }, ensure_ascii=False, indent=2)
        
    logger
    
    return product_details

async def find_two_product(user_message, db_session_factory):
    try:
        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(find_p_in_fifth_scenario(user_message, 1, db_session_factory))
            task2 = tg.create_task(find_p_in_fifth_scenario(user_message, 2, db_session_factory))
            # task1 = tg.create_task(find_random_keys(user_message, db_session_factory))
            
            task3 = tg.create_task(get_calculate_code(user_message))
        
        first_product = task1.result()
        second_product = task2.result()
        # first_product, second_product = task1.result()
        
        code_to_get_info = task3.result()
        
        return (first_product, second_product, code_to_get_info)

    except* Exception as eg:
        logger.error("An error occurred in one of the tasks. Details:")
        for exc in eg.exceptions:
            logger.error(f"  - Exception: {exc}", exc_info=True)


async def find_p_in_fifth_scenario(user_message, index, db_session_factory)->str:
    async with db_session_factory() as db:
        if index == 1:
            index_str = 'اول'
        elif index == 2:
            index_str = 'دوم'
        else:
            raise ValueError("index should be 1 or 2")
        user_message = f"مقایسه زیر رو ببین\n\n{user_message}\n\n در این مقایسهدمبال محصول {index_str} هستم."
        user_message = f"find the {index_str} product in this compare request:\n\n{user_message}"
        #embed
        # found_key = await find_exact_product_name_service_and_embed(user_message, None)
        #old
        found_key = await find_exact_product_name_service(user_message = user_message, db=db, possible_product_name=None)
        product = await repository.get_product_by_random_key(db=db, random_key=found_key)
        
        # system_prompt = SCENARIO_FIVE_PROMPTS.get("find_p_prompt", "").format(
        #     index_str=index_str,
        # )
        
        # tool_handler = ToolHandler(db=db)
        # tools_answer = []

        # llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        #     message=user_message,
        #     systemprompt=system_prompt,
        #     model="gpt-4.1-mini",
        #     tools=OLD_FIRST_SCENARIO_TOOLS,
        #     tools_answer=None
        # )

        # for _ in range(5):
        #     if tool_calls:
        #         tools_answer = await tool_handler.handle_tool_call(tool_calls, tools_answer)
                
        #         llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        #             message=user_message,
        #             systemprompt=system_prompt,
        #             model="gpt-4.1-mini",
        #             tools=OLD_FIRST_SCENARIO_TOOLS,
        #             tools_answer=tools_answer
        #         )
        #     else:
        #         break
        
        # logger.info(f"llm_response for index {index}: {llm_response}")
        
        # if not llm_response:
        #     logger.warning(f"LLM did not return a response for index {index}.")
        #     return None
            
        # p_name = llm_response.split('\n')[0].strip()
        # logger.info(f"cleaned name for index {index}:{p_name}")
        
        # از همان سشن 'db' برای کوئری‌های ریپازیتوری استفاده کنید
        # product = await repository.get_product_by_name_like(db=db, product_name=p_name)
        # if not product:
        #     logger.info("No matching product keys found. trying to search by like.")
        #     product = await repository.get_product_by_name_like(db=db, product_name=p_name)            
        logger.info(f"product for index {index}: {str(product.persian_name)}")
        return product
    
    
async def find_random_keys(user_message, db_session_factory)->str:
    async with db_session_factory() as db:

        system_prompt = SCENARIO_FIVE_PROMPTS.get("find_random_keys", "")
        
        llm_response = await simple_openai_gpt_request(
            message=user_message,
            systemprompt=system_prompt,
            model="gpt-4.1-mini"
        )

        if "```json" in llm_response:
            llm_response = llm_response.split("```python")[1].split("```")[0].strip()
        data = json.loads(llm_response)

        product_rkey_1 = data['product_1_id']
        product_rkey_2 = data['product_2_id']
        product_1 = await repository.get_product_by_random_key(db=db, random_key=product_rkey_1)
        product_2 = await repository.get_product_by_random_key(db=db, random_key=product_rkey_2)
        if not product_1 or not product_2:
            logger.info("No matching product keys found. trying to search by like.")
                        
        logger.info(f"products: {str(product_1.persian_name)},   {str(product_2.persian_name)}")
        return product_1, product_2


async def get_calculate_code(user_request):
    system_prompt = SCENARIO_FIVE_PROMPTS.get("calculate_prompt", "").format(
        user_query=user_request,
    )
    llm_response_code = await simple_openai_gpt_request(
        message='',
        systemprompt=system_prompt,
        model="gpt-4.1",
    )
    if "```python" in llm_response_code:
        llm_response_code = llm_response_code.split("```python")[1].split("```")[0].strip()

    logger.info(f"-> Generated Python code from LLM:\n{llm_response_code}")
    return llm_response_code
    

async def find_exact_product_name_service(user_message: str, db: AsyncSession, possible_product_name: str) -> Optional[str]:
    if possible_product_name:
        product_names = await repository.find_similar_products(
            db=db,
            product_name=possible_product_name,
        )
    else:
        product_names = "use function to search"
    system_prompt = SELECT_BEST_MATCH_PROMPT.get("new_main_prompt_template_embed", "").format(
        user_query = user_message,
        search_results_str=str(product_names)
    )
    llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        message="",
        systemprompt=system_prompt,
        model="gpt-4.1-mini",
        tools=EMBED_FIRST_SCENARIO_TOOLS
    )
    tools_answer = []
    for _ in range(5):
        if tool_calls: 
            for tool_call in tool_calls:
                function_arguments = tool_call.function.arguments
                function_name = tool_call.function.name
                parsed_arguments = json.loads(function_arguments)
                logger.info(f"function_name = {function_name}\nfunction_arguments: {str(function_arguments)}")
                possible_product_name = parsed_arguments.get("product_name")
                product_names = await repository.find_similar_products(db, possible_product_name)
                tools_answer.append({"role": "assistant", "tool_calls": [{"id": tool_call.id, "type": "function", "function": {"name": function_name, "arguments": function_arguments}}]})
                tools_answer.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(product_names)})
            llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
                message=user_message,
                systemprompt=system_prompt,
                model="gpt-4.1-mini",
                tools=EMBED_FIRST_AGENT_TOOLS,
                tools_answer=tools_answer
            )
        else:
            break
    
    logger.info(f"llm_response: {llm_response}")
    found_key = llm_response.split('\n')[0]
    found_key = found_key.strip()
    logger.info(f"found_key:{found_key}")
    return found_key

    
# async def find_exact_product_name_service(user_message: str, db: AsyncSession, essential_keywords: List[str], descriptive_keywords: List[str]) -> Optional[str]:
#     product_names = await repository.search_products_by_keywords(
#         db=db,
#         essential_keywords=essential_keywords,
#         descriptive_keywords=descriptive_keywords
#     )
#     if not product_names:
#         product_names =  json.dumps({"status": "not_found", "message": """No products found matching the keywords.\ntry using some essential_keywords in descriptive_keywords or change keywords if still getting this error"""})
    
#     if len(product_names) > 100:
#         logger.warning(f"""Too many results ({len(product_names)})""")
#         product_names = json.dumps({"status": """too_many_results\nThe search is too general.\n try using some specific keywords in essential_keywords or adding new keywords to your search.""", "count": len(product_names)})
#     system_prompt = SELECT_BEST_MATCH_PROMPT.get("main_prompt_template", "").format(
#         user_query = user_message,
#         search_results_str=product_names
#     )
#     tool_handler = ToolHandler(db=db)
#     llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
#         message="",
#         systemprompt=system_prompt,
#         model="gpt-4.1-nano",
#         tools=FIRST_SCENARIO_TOOLS
#     )
#     tools_answer = []
#     for _ in range(5):
#         if tool_calls:
#             tools_answer = await tool_handler.handle_tool_call(tool_calls, tools_answer)
            
#             llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
#                 message=user_message,
#                 systemprompt=system_prompt,
#                 model="gpt-4.1-mini",
#                 tools=FIRST_SCENARIO_TOOLS,
#                 tools_answer=tools_answer
#             )
#         else:
#             break
    
#     logger.info(f"llm_response: {llm_response}")
#     p_name = llm_response.split('\n')[0]
#     p_name = p_name.strip()
#     logger.info(f"cleaned name:{p_name}")
#     found_keys = await repository.search_product_by_name(db=db, product_name=p_name)
#     if not found_keys:
#         logger.info("No matching product keys found.trying to search by like.")
#         found_keys = await repository.get_product_rkey_by_name_like(db=db, product_name=p_name)
#     logger.info(f"found_keys: {found_keys}")
#     return found_keys[0] if found_keys else None

async def old_find_exact_product_name_service(user_message: str, db: AsyncSession, previous_keywords = None, search_result=None, user_query=None ) -> Optional[str]:
    system_prompt = OLD_FIND_PRODUCT_PROMPTS.get("v2_prompt", "").format(
        user_query = user_query,
        search_result = search_result,
        previous_keywords = previous_keywords,
    )
    tool_handler = ToolHandler(db=db)
    llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        message=user_message,
        systemprompt=system_prompt,
        model="gpt-4.1-mini",
        tools=OLD_FIRST_SCENARIO_TOOLS
    )
    tools_answer = []
    for _ in range(5):
        if tool_calls:
            tools_answer = await tool_handler.handle_tool_call(tool_calls, tools_answer)
            
            llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
                message=user_message,
                systemprompt=system_prompt,
                model="gpt-4.1-mini",
                tools=OLD_FIRST_SCENARIO_TOOLS,
                tools_answer=tools_answer
            )
        else:
            break
    
    logger.info(f"llm_response: {llm_response}")
    p_name = llm_response.split('\n')[0]
    p_name = p_name.strip()
    logger.info(f"cleaned name:{p_name}")
    found_keys = await repository.search_product_by_name(db=db, product_name=p_name)
    if not found_keys:
        logger.info("No matching product keys found.trying to search by like.")
        found_keys = await repository.get_product_rkey_by_name_like(db=db, product_name=p_name)
    logger.info(f"found_keys: {found_keys}")
    return found_keys[0] if found_keys else None


async def find_exact_product_name_service_and_embed(user_message: str, possible_product_name) -> str:
    if possible_product_name:
        product_names = await semantic_search(possible_product_name)
        if not product_names:
            product_names =  "have not found anything"
        
        # if len(product_names) > 100:
        #     logger.warning(f"""Too many results ({len(product_names)})""")
        #     product_names = f"Too many results ({len(product_names)})"
    else:
        product_names = "use function to search"
    system_prompt = SELECT_BEST_MATCH_PROMPT.get("new_main_prompt_template_embed", "").format(
        user_query = user_message,
        search_results_str=product_names
    )
    llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        message="",
        systemprompt=system_prompt,
        model="gpt-4.1-mini",
        tools=EMBED_FIRST_SCENARIO_TOOLS
    )
    tools_answer = []
    for _ in range(5):
        if tool_calls: 
            for tool_call in tool_calls:
                function_arguments = tool_call.function.arguments
                function_name = tool_call.function.name
                parsed_arguments = json.loads(function_arguments)
                logger.info(f"function_name = {function_name}\nfunction_arguments: {str(function_arguments)}")
                possible_product_name = parsed_arguments.get("product_name")
                result = await semantic_search(possible_product_name)
                tools_answer.append({"role": "assistant", "tool_calls": [{"id": tool_call.id, "type": "function", "function": {"name": function_name, "arguments": function_arguments}}]})
                tools_answer.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
            llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
                message=user_message,
                systemprompt=system_prompt,
                model="gpt-4.1-mini",
                tools=EMBED_FIRST_AGENT_TOOLS,
                tools_answer=tools_answer
            )
        else:
            break
    
    logger.info(f"llm_response: {llm_response}")
    found_key = llm_response.split('\n')[0]
    found_key = found_key.strip()
    logger.info(f"found_key:{found_key}")
    return found_key



async def search_embed(user_query, keywords):
    
    url = "https://vector-search.darkube.app/hybrid-search/"
    payload = {
        "query": user_query,
        "keywords": keywords
    }
    logger.info(f"sending to semantic search: query:{user_query}\nkeywords:{keywords}\n")
    
    results = await post_async_request(url, payload)

    if results is None:
        logger.error("❌ No results received from post_async_request.")
        return "❌ No results received from post_async_request."

    logger.info(f"result:{json.dumps(results, ensure_ascii=False)}")
    
    if isinstance(results, list):
        for item in results:
            if 'score' in item:
                del item['score']
    
    return json.dumps(results, ensure_ascii=False)


async def semantic_search(user_query):
    
    url = "https://vector-search.darkube.app/semantic-search/"
    payload = {
        "query": user_query,
        
    }
    logger.info(f"sending to semantic search: query:{user_query}\n")
    
    results = await post_async_request(url, payload)

    if results is None:
        logger.error("❌ No results received from post_async_request.")
        return "❌ No results received from post_async_request."

    logger.info(f"result:{json.dumps(results, ensure_ascii=False)}")
    
    if isinstance(results, list):
        for item in results:
            if 'score' in item:
                del item['score']
    
    return json.dumps(results, ensure_ascii=False)
# async def get_embedding_vector(text_query: str) -> Optional[List[float]]:
#     """
#     متن را به سرور امبدینگ فرستاده و وکتور امبدینگ را دریافت می‌کند.
#     """
#     logger.info(f"Requesting embedding for text: '{text_query}'")
#     payload = {"text": text_query}
#     response = await post_async_request("http://89.169.32.124:2256/embed", payload)

#     if response and "embedding" in response:
#         logger.info("✅ Embedding vector successfully received.")
#         return response["embedding"]
#     else:
#         logger.error("❌ Failed to get embedding vector from the server.")
#         return None
    
    
# async def search_with_text(text_query: str, keywords: List[str]):
#     """
#     فرآیند کامل جستجو را مدیریت می‌کند: ابتدا امبدینگ را گرفته و سپس جستجو را انجام می‌دهد.
#     """
#     # مرحله ۱: دریافت وکتور امبدینگ از سرور امبدینگ
#     embedding_vector = await get_embedding_vector(text_query)

#     if not embedding_vector:
#         logger.error("Search process terminated because embedding could not be generated.")
#         return None

#     # مرحله ۲: آماده‌سازی payload برای سرور جستجوی وکتور
#     logger.info("Preparing payload for vector search server...")
#     search_payload = {
#         "embedding": embedding_vector,
#         "keywords": keywords
#     }

#     # مرحله ۳: ارسال درخواست به سرور جستجو
#     search_results = await post_async_request("https://vector-search.darkube.app/hybrid-search/", search_payload)
    
    # return search_results