import json
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from typing import Dict, Tuple, List, Any, Optional

from app.schemas.chat import ChatResponse
from app.schemas.state import Scenario4State
from app.core.logger import logger
from app.db import repository
from app.services.openai_service import simple_openai_gpt_request
from app.llm.prompts import SCENARIO_FOUR_PROMPTS
from .utils import Utils

# In-memory storage for conversational sessions.
# For a production application, this should be replaced with a proper cache like Redis.
_sessions: Dict[str, Scenario4State] = {}

def is_active_session(chat_id: str) -> bool:
    """Checks if a conversational session is currently active for the given chat_id."""
    return chat_id in _sessions

async def handle(request, db: AsyncSession) -> ChatResponse:
    """
    Handles Scenario 4: Conversational Search.

    This function manages a multi-turn conversation with the user to help them
    find a product by progressively refining their search criteria. It uses an
    in-memory state machine to track the conversation's progress.

    Args:
        chat_id: The ID of the current chat session.
        user_message: The latest message from the user.
        db: The async database session.

    Returns:
        A ChatResponse object, which could be a message to the user or the
        final selected member keys.
    """
    user_message = request.messages[-1].content.strip()
    chat_id = request.chat_id
    session = _sessions.get(chat_id, Scenario4State())
    session.chat_history.append({"role": "user", "content": user_message})

    response_message = None
    final_response = None

    try:
        # Emergency state if conversation gets too long
        response_message = "سلام اگه امکانش هست کامل توضیح بدید چی میخواید تا بتونم بهتر کمکتون کنم\nدرباره فروشنده گارانتی یا قیمت"
        if len(session.chat_history) > 9:
            logger.warning(f"Session {chat_id} entering emergency state due to length.")
            final_keys, session = await _handle_emergency_state(user_message, db, session)
            final_response = ChatResponse(member_random_keys=final_keys)

        elif session.state == 1:
            response_message, session = await _handle_state_1(user_message, db, session)
        elif session.state == 2:
            response_message, session = await _handle_state_2(user_message, db, session)
        elif session.state == 3:
            response_message, session = await _handle_state_3(user_message, session)
        elif session.state == 4:
            response_message, session, is_done = await _handle_state_4(user_message, session)
            if is_done:
                final_response = ChatResponse(member_random_keys=response_message)


        if final_response:
            logger.info(f"Conversational search for chat_id {chat_id} concluded. Cleaning up session.")
            if chat_id in _sessions:
                del _sessions[chat_id]
            return final_response

        session.chat_history.append({"role": "assistant", "content": response_message})
        _sessions[chat_id] = session
        return ChatResponse(message=response_message)

    except Exception as e:
        logger.error(f"An error occurred in Scenario 4 for chat_id {chat_id}: {e}", exc_info=True)
        if chat_id in _sessions:
            del _sessions[chat_id]
        raise HTTPException(status_code=500, detail="An unexpected error occurred during our conversation. Please start over.")


async def _handle_state_1(user_message: str, db: AsyncSession, session: Scenario4State) -> Tuple[str, Scenario4State]:
    """State 1: Greet the user, ask clarifying questions, and identify product category."""
    logger.info(f"Scenario 4, State 1 for chat_id: {session.chat_history}")
    assistant_message = await simple_openai_gpt_request(
        message=user_message,
        systemprompt=SCENARIO_FOUR_PROMPTS["system_prompt"],
        model="gpt-4.1-mini",
        chat_history=session.chat_history
    )

    categories = await repository.get_all_categories(db)
    chosen_category = await simple_openai_gpt_request(
        message=user_message,
        systemprompt=SCENARIO_FOUR_PROMPTS["extract_category"].format(categories=categories),
        model="gpt-5-mini"
    )

    if chosen_category:
        category_sample = await repository.get_category_features_example(db, chosen_category)
        if category_sample:
            schema_as_string = json.dumps(category_sample, ensure_ascii=False)
            session.product_features = schema_as_string
            logger.info(f"Found category '{chosen_category}' and stored its schema.")
        else:
            session.product_features = "{}"
            logger.warning(f"Category '{chosen_category}' found, but no feature schema available.")
    else:
        session.product_features = "{}"
        logger.warning("Could not determine a product category from the user's query.")

    session.state = 2
    return assistant_message, session

async def _handle_state_2(user_message: str, db: AsyncSession, session: Scenario4State) -> Tuple[str, Scenario4State]:
    """State 2: Extract filters, search for products, and handle results."""
    logger.info("Scenario 4, State 2")
    history = session.chat_history
    history_str = "\n".join([f"{chat['role']}: {chat['content']}" for chat in session.chat_history])

    system_prompt_extract = SCENARIO_FOUR_PROMPTS["new_extract_info"].format(
        chat_history=history_str,
        feature_schema_json=session.product_features
    )
    llm_response_str = await simple_openai_gpt_request(message="",
        systemprompt=system_prompt_extract, 
        model="gpt-4.1"
    )
    
    
    logger.info(f"LLM filter extraction response:\n {llm_response_str}")

    try:
        filters_json = Utils.parse_llm_json_response(llm_response_str)
        session.filters_json = filters_json
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Error parsing LLM filter response: {e}")
        return "I'm having a little trouble understanding the details. Could you please rephrase your requirements?", session

    # Find products based on the extracted filters
    products = await repository.find_products_with_aggregated_sellers_with_features(db, filters_json)
    session.products_with_sellers = products
    logger.info(f"Found {len(products)} products matching the criteria.")

    navigator_prompt = SCENARIO_FOUR_PROMPTS["state_2_path"]
    input_for_navigator_prompt = {}

    if len(products) >= 1:
        logger.info("Path A: Success, 1-5 results found.")
        input_for_navigator_prompt = {
            "action_mode": "HANDLE_SUCCESSFUL_RESULTS",
            "search_results": products,
            "last_search_parameters": filters_json,
            "chat_history": str(history)
        }
        session.state = 3
        
    elif len(products) == 0:
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
            
            second_attempt_products = await repository.find_products_with_aggregated_sellers_with_features(db, updated_filters_for_db)
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

async def _handle_state_3(user_message: str, db, session: Scenario4State) -> Tuple[str, Scenario4State]:
    """State 3: Present product options and ask the user to choose."""
    logger.info(f"Scenario 4, State 3 for chat_id: {session.chat_history}")
    history = session.chat_history
    products_with_sellers = session.products_with_sellers
    filters_json = session.filters_json
    logger.info(f"products_with_sellers in state 3:\n{str(products_with_sellers)}")
    if not products_with_sellers:
        raise HTTPException(status_code=404, detail="No products found in previous steps.")
    
    system_prompt = SCENARIO_FOUR_PROMPTS["final_recommendation"]
    input_for_selection = {
        "user_response": user_message,
        "product_options": str(products_with_sellers)
    }
    llm_response = await simple_openai_gpt_request(
        message=json.dumps(input_for_selection),
        systemprompt=system_prompt,
        model="gpt-4.1",
    )
    
    json_from_llm = Utils.parse_llm_json_response(llm_response)
    selected_product_name = json_from_llm.get("selected_product_name")

    if not selected_product_name:
        session.state = 2
        return await _handle_state_2(user_message, db, session)

    selected_product = next((p for p in products_with_sellers if p['product_name'] == selected_product_name), None)
    
    if not selected_product:
        session.state = 2
        return await _handle_state_2(user_message, db, session)

    session.selected_product = selected_product
    session.state = 4

    present_sellers_prompt = SCENARIO_FOUR_PROMPTS["present_sellers"].format(
        product_name=selected_product['product_name'],
        sellers_list=json.dumps(selected_product['sellers'], ensure_ascii=False)
    )
    
    response_message = await simple_openai_gpt_request(
        message="",
        systemprompt=present_sellers_prompt,
        model="gpt-4.1-mini"
    )

    return response_message, session


async def _handle_state_4(user_message: str, session: Scenario4State) -> Tuple[Optional[List[str]], Scenario4State, bool]:
    """State 4: User has chosen a product, now present sellers for final selection."""
    logger.info(f"Scenario 4, State 4 for chat_id: {session.chat_history}")

    selected_product = session.selected_product
    if not selected_product:
        raise HTTPException(status_code=404, detail="محصولی انتخاب نشده است.")

    system_prompt = SCENARIO_FOUR_PROMPTS["select_seller"].format(
        user_response=user_message,
        seller_options=str(selected_product['sellers'])
    )

    llm_response = await simple_openai_gpt_request(
        message="",
        systemprompt=system_prompt,
        model="gpt-4.1",
    )
    
    json_from_llm = Utils.parse_llm_json_response(llm_response)
    selected_member_key = json_from_llm.get("selected_member_key")

    if not selected_member_key:
        final_message = "متاسفانه نتوانستم فروشنده مورد نظر شما را پیدا کنم. لطفاً دوباره تلاش کنید."
        return final_message, session, False

    return [selected_member_key], session, True

async def _handle_emergency_state(user_message: str, db: AsyncSession, session: Scenario4State) -> Tuple[Optional[List[str]], Scenario4State]:
    """Emergency State: If conversation is too long, force a selection."""
    logger.warning(f"Handling emergency state for chat: {session.chat_history}")
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
        model="gpt-5",
    )
    logger.info(f"llm_response in state 3:\n{str(llm_response)}")

    json_from_llm = Utils.parse_llm_json_response(llm_response)

    
    final_user_message = json_from_llm.get("selected_member_key")


    member_key = final_user_message

    
    return [member_key], session, True