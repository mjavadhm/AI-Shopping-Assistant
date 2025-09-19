import asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Tuple 
import json
# import aiohttp
import json

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.openai_service import simple_openai_gpt_request, simple_openai_gpt_request_with_tools
from app.llm.prompts import (FIND_PRODUCT_PROMPTS, FIRST_AGENT_PROMPT, ROUTER_PROMPT, 
    SCENARIO_THREE_PROMPTS, SCENARIO_TWO_PROMPTS, SELECT_BEST_MATCH_PROMPT, OLD_FIND_PRODUCT_PROMPTS, SCENARIO_FIVE_PROMPTS)
from app.db.session import get_db
from app.db.session import AsyncSessionLocal
from app.llm.tools.definitions import FIRST_AGENT_TOOLS, FIRST_SCENARIO_TOOLS, OLD_FIRST_SCENARIO_TOOLS, EMBED_FIRST_AGENT_TOOLS
from app.llm.tools.handler import ToolHandler
from app.core.http_client import post_async_request
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
            
            #with full text search
            # scenario, essential_keywords, descriptive_keywords = await classify_scenario(request)
            
            # logger.info(f"CLASSIFIED SCENARIO: {scenario}, ESSENTIAL: {essential_keywords}, DESCRIPTIVE: {descriptive_keywords}")
            # found_key = await find_exact_product_name_service(user_message = request.messages[-1].content.strip(), db=db, essential_keywords=essential_keywords, descriptive_keywords=descriptive_keywords)
            # if not found_key and scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_2_FEATURE_EXTRACTION", "SCENARIO_3_SELLER_INFO"]:
            #     raise HTTPException(status_code=404, detail="No products found matching the keywords.")
            #------------------------------------------
            #with keyword simple
            scenario = await old_classify_scenario(request)
            logger.info(f"CLASSIFIED SCENARIO: {scenario}")
            if scenario != "SCENARIO_5_COMPARISON":
                
                found_key = await old_find_exact_product_name_service(user_message = request.messages[-1].content.strip(), db=db)
                logger.info(f"found_key: {found_key}")
            #-----------------------------------------------------
            #with embed
            #---------------------------------------------
            # keywords = []
            # scenario, keywords = await classify_scenario_for_embed(request)
            # logger.info(f"CLASSIFIED SCENARIO: {scenario}, KEYWORDS: {keywords}")
            # if scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_2_FEATURE_EXTRACTION", "SCENARIO_3_SELLER_INFO"]:
            #     found_key = await find_exact_product_name_service_and_embed(user_message = request.messages[-1].content.strip(), keywords=keywords)
            # if not found_key and scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_2_FEATURE_EXTRACTION", "SCENARIO_3_SELLER_INFO"]:
            #     raise HTTPException(status_code=404, detail="No products found matching the keywords.")
            
            
            # return ChatResponse(base_random_keys=[found_key])
            if scenario == "SCENARIO_1_DIRECT_SEARCH":
                return ChatResponse(base_random_keys=[found_key]) 
                # response = await scenario_one(request, db=db, essential_keywords=essential_keywords, descriptive_keywords=descriptive_keywords)
            elif scenario == "SCENARIO_2_FEATURE_EXTRACTION":
                response = await scenario_two(request, db=db, found_key=found_key)
            elif scenario == "SCENARIO_3_SELLER_INFO":
                response = await scenario_three(request, db=db, found_key=found_key)
            # elif scenario == "SCENARIO_4_CONVERSATIONAL_SEARCH":
            #     response = await scenario_three(request, db=db, found_key=found_key)
            elif scenario == "SCENARIO_5_COMPARISON":
                response = await scenario_five(request, db=db)
        return response
    except Exception as e:
        logger.error(e,exc_info=True)


async def classify_scenario_for_embed(request: ChatRequest) -> Tuple[str, List[str]]:
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
            tools=EMBED_FIRST_AGENT_TOOLS
        )

        scenario = "UNCATEGORIZED"
        keywords = []
        
        if not tool_calls:
            logger.warning("No tool calls returned from the model.")
            return scenario, keywords

        for tool_call in tool_calls:
            logger.info(f"Processing tool call: {tool_call.function.name}")
            try:
                parsed_args = json.loads(tool_call.function.arguments)
                if tool_call.function.name == "classify_user_request":
                    scenario = parsed_args.get("scenario", "UNCATEGORIZED")
                elif tool_call.function.name == "extract_search_keywords":
                    keywords = parsed_args.get("product_name_keywords", [])

            except json.JSONDecodeError:
                logger.error(f"Failed to parse arguments for tool {tool_call.function.name}")

        return scenario, keywords
        
    except Exception as e:
        logger.error(e, exc_info=True)
        return "UNCATEGORIZED", []




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
            message=last_message,
            systemprompt=system_prompt,
            model="gpt-4.1-nano",
                    
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
    
    
    
async def scenario_five(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    user_message = request.messages[-1].content.strip()
    logger.info("Initiating Scenario 5: Product Comparison.")

    product_data = await find_two_product(user_message, AsyncSessionLocal)

    if product_data is None:
        logger.error("Failed to retrieve data for one or both products in comparison.")
        raise HTTPException(status_code=500, detail="Could not process the comparison due to an internal error.")

    first_product, second_product = product_data

    product_map = {
        first_product.persian_name: first_product.random_key,
        second_product.persian_name: second_product.random_key
    }

    product_1_details = json.dumps({
        "persian_name": first_product.persian_name,
        "features": first_product.extra_features or {}
    }, ensure_ascii=False, indent=2)

    product_2_details = json.dumps({
        "persian_name": second_product.persian_name,
        "features": second_product.extra_features or {}
    }, ensure_ascii=False, indent=2)


    comparison_system_prompt = SCENARIO_FIVE_PROMPTS.get("comparison_prompt").format(
        user_query=user_message,
        product_1_details=product_1_details,
        product_2_details=product_2_details
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

        winning_key = product_map.get(winning_name)
        
        logger.info(f"LLM selected winner: '{winning_name}' with key: {winning_key}")

        return ChatResponse(
            message=text_explanation,
            base_random_keys=[winning_key] if winning_key else []
        )

    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Could not parse LLM response for comparison: {e}")
        # اگر LLM فرمت را رعایت نکرد، کل متنش را به عنوان پاسخ برمی‌گردانیم
        return ChatResponse(message=final_response_text)

    

async def find_two_product(user_message, db_session_factory):
    try:
        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(find_p_in_fifth_scenario(user_message, 1, db_session_factory))
            task2 = tg.create_task(find_p_in_fifth_scenario(user_message, 2, db_session_factory))
        
        
        first_product = task1.result()
        second_product = task2.result()
        
        return (first_product, second_product)

    except* Exception as eg:
        logger.error("An error occurred in one of the tasks. Details:")
        for exc in eg.exceptions:
            logger.error(f"  - Exception: {exc}", exc_info=True)


async def find_p_in_fifth_scenario(user_message, index, db_session_factory)->str:
    async with db_session_factory() as db:
        if index == 1:
            index_str = 'first'
        elif index == 2:
            index_str = 'second'
        else:
            raise ValueError("index should be 1 or 2")

        system_prompt = SCENARIO_FIVE_PROMPTS.get("find_p_prompt", "").format(
            index_str=index_str,
        )
        
        tool_handler = ToolHandler(db=db)
        tools_answer = []

        llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
            message=user_message,
            systemprompt=system_prompt,
            model="gpt-4.1-mini",
            tools=OLD_FIRST_SCENARIO_TOOLS,
            tools_answer=None
        )

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
        
        logger.info(f"llm_response for index {index}: {llm_response}")
        
        if not llm_response:
            logger.warning(f"LLM did not return a response for index {index}.")
            return None
            
        p_name = llm_response.split('\n')[0].strip()
        logger.info(f"cleaned name for index {index}:{p_name}")
        
        # از همان سشن 'db' برای کوئری‌های ریپازیتوری استفاده کنید
        product = await repository.get_product_by_name_like(db=db, product_name=p_name)
        if not product:
            logger.info("No matching product keys found. trying to search by like.")
            product = await repository.get_product_by_name_like(db=db, product_name=p_name)            
        logger.info(f"product for index {index}: {str(product.persian_name)}")
        return product

async def find_exact_product_name_service(user_message: str, db: AsyncSession, essential_keywords: List[str], descriptive_keywords: List[str]) -> Optional[str]:
    product_names = await repository.search_products_by_keywords(
        db=db,
        essential_keywords=essential_keywords,
        descriptive_keywords=descriptive_keywords
    )
    if not product_names:
        product_names =  json.dumps({"status": "not_found", "message": """No products found matching the keywords.\ntry using some essential_keywords in descriptive_keywords or change keywords if still getting this error"""})
    
    if len(product_names) > 100:
        logger.warning(f"""Too many results ({len(product_names)})""")
        product_names = json.dumps({"status": """too_many_results\nThe search is too general.\n try using some specific keywords in essential_keywords or adding new keywords to your search.""", "count": len(product_names)})
    system_prompt = SELECT_BEST_MATCH_PROMPT.get("main_prompt_template", "").format(
        user_query = user_message,
        search_results_str=product_names
    )
    tool_handler = ToolHandler(db=db)
    llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        message="",
        systemprompt=system_prompt,
        model="gpt-4.1-nano",
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
    if not found_keys:
        logger.info("No matching product keys found.trying to search by like.")
        found_keys = await repository.get_product_rkey_by_name_like(db=db, product_name=p_name)
    logger.info(f"found_keys: {found_keys}")
    return found_keys[0] if found_keys else None

async def old_find_exact_product_name_service(user_message: str, db: AsyncSession) -> Optional[str]:
    system_prompt = OLD_FIND_PRODUCT_PROMPTS.get("main_prompt", "")
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


async def find_exact_product_name_service_and_embed(user_message: str, keywords) -> str:
    product_names = await search_embed(user_message, keywords)
    if not product_names:
        product_names =  "have not found anything"
    
    if len(product_names) > 100:
        logger.warning(f"""Too many results ({len(product_names)})""")
        product_names = f"Too many results ({len(product_names)})"
    system_prompt = SELECT_BEST_MATCH_PROMPT.get("new_main_prompt_template_embed", "").format(
        user_query = user_message,
        search_results_str=product_names
    )
    llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
        message="",
        systemprompt=system_prompt,
        model="gpt-4.1-mini",
        tools=EMBED_FIRST_AGENT_TOOLS
    )
    tools_answer = []
    for _ in range(5):
        if tool_calls: 
            for tool_call in tool_calls:
                function_arguments = tool_call.function.arguments
                function_name = tool_call.function.name
                keywords = function_arguments.get("product_name_keywords")
                result = await search_embed(user_message, keywords)
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
    
    url = "https://semantic-search.darkube.app"
    payload = {
        "query": user_query,
        "keywords": keywords
    }
    logger.info(f"sending to semantic search: query:{user_query}\nkeywords:{keywords}\n")
    
    response = await post_async_request(url,payload)
    results = await response.json()
    logger.info(f"result:{json.dumps(results, ensure_ascii=False).encode('utf-8')}")
    for item in results:
        del item['score']
    return json.dumps(results, ensure_ascii=False)