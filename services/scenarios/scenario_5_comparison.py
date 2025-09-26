import json
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.schemas.chat import ChatRequest, ChatResponse
from app.core.logger import logger
from app.services.openai_service import simple_openai_gpt_request
from app.llm.prompts import SCENARIO_FIVE_PROMPTS
from app.db import repository
from app.db.session import AsyncSessionLocal
from utils import Utils

async def handle(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    """
    Handles Scenario 5: Product Comparison.

    This function orchestrates a multi-step process to compare two products:
    1. Identifies the two products from the user's query.
    2. Generates and executes code to analyze seller data for each.
    3. Uses an LLM to perform the final comparison and select a winner.

    Args:
        request: The incoming chat request object.
        db: The async database session.

    Returns:
        A ChatResponse containing the comparison result and the winning product's key.
    """
    logger.info("Handling Scenario 5: Product Comparison.")
    user_message = request.messages[-1].content.strip()

    try:
        # Step 1: Concurrently find both products and the analysis code
        product_1, product_2, analysis_code = await _find_products_and_get_code(user_message, AsyncSessionLocal)

        if not product_1 or not product_2:
            raise HTTPException(status_code=404, detail="Could not identify one or both products for comparison.")

        logger.info(f"First product key: {product_1.random_key if product_1 else 'None'}")
        product_1_details = await _get_product_details_for_comparison(db, product_1, analysis_code)
        logger.info(f"product_1_details: {product_1_details}")
        logger.info(f"Second product key: {product_2.random_key if product_2 else 'None'}")
        product_2_details = await _get_product_details_for_comparison(db, product_2, analysis_code)
        logger.info(f"product_2_details: {product_2_details}")

        # Step 3: Use LLM for the final comparison
        comparison_prompt = SCENARIO_FIVE_PROMPTS.get("comparison_prompt").format(
            user_query=user_message,
            product_1_details=product_1_details,
            product_2_details=product_2_details,
            product_1_key=product_1.random_key,
            product_2_key=product_2.random_key
        )

        final_llm_response = await simple_openai_gpt_request(
            message="",
            systemprompt=comparison_prompt,
            model="gpt-4.1-mini"
        )

        return _parse_final_comparison_response(final_llm_response)

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"An unexpected error occurred in Scenario 5 handler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during the product comparison.")


async def _find_products_and_get_code(user_message: str, db_session_factory):
    """Concurrently finds two products and generates analysis code from the user's query."""
    try:
        # Running tasks in parallel for efficiency
        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(_find_single_product_for_comparison(user_message, db_session_factory, "اول"))
            task2 = tg.create_task(_find_single_product_for_comparison(user_message, db_session_factory, "دوم"))
            task3 = tg.create_task(_get_analysis_code_from_llm(user_message))
        
        return task1.result(), task2.result(), task3.result()
    except* Exception as eg:
        logger.error(f"Error during concurrent product finding/code generation: {eg.exceptions}")
        raise HTTPException(status_code=500, detail="Failed to prepare data for comparison.")


async def _find_single_product_for_comparison(user_message: str, db_session_factory, index_str: str):
    """Finds one of the products mentioned in the user's comparison query."""

    user_message = f"مقایسه زیر رو ببین\n\n{user_message}\n\n در این مقایسه دنبال محصول {index_str} هستم."
    async with db_session_factory() as db:
        #embed
        # found_key = await find_exact_product_name_service_and_embed(user_message, None)
        #old
        found_key = await Utils.find_exact_product_name_service(user_message = user_message, db=db, possible_product_name=None)
        product = await repository.get_product_by_random_key(db=db, random_key=found_key)
        if not product:
            logger.warning(f"Could not find {index_str}")
        return product

async def _get_analysis_code_from_llm(user_message: str) -> str:
    """Generates Python code via LLM to analyze seller data based on user's query."""
    prompt = SCENARIO_FIVE_PROMPTS.get("calculate_prompt", "").format(user_query=user_message)
    code_response = await simple_openai_gpt_request(message='', systemprompt=prompt, model="gpt-4.1")

    if "```python" in code_response:
        return code_response.split("```python")[1].split("```")[0].strip()
    return code_response.strip()


async def _get_product_details_for_comparison(db: AsyncSession, product: repository.models.BaseProduct, code: str) -> str:
    """Compiles a detailed JSON string for a single product for the final comparison."""
    sellers_context = await Utils.get_sellers_context_by_key(db, product.random_key)
    
    calculated_info = None
    if code and "return None" not in code:
        try:
            calculated_info = Utils.execute_generated_code(code, sellers_context)
        except Exception as e:
            logger.warning(f"Failed to execute generated code for product {product.random_key}: {e}")
            calculated_info = "Error in analysis"
    
    details = {
        "random_key(id)": product.random_key,
        "persian_name": product.persian_name,
        "features": product.extra_features or {},
    }
    if calculated_info:
        details["sellers_info"] = str(calculated_info)
        
    return json.dumps(details, ensure_ascii=False, indent=2)


def _parse_final_comparison_response(llm_response: str) -> ChatResponse:
    """Parses the LLM's final comparison output (JSON + text) into a ChatResponse."""
    try:
        json_part_str = llm_response.split("```json")[1].split("```")[0]
        text_explanation = llm_response.split("```")[-1].strip()

        response_json = json.loads(json_part_str)
        winning_key = response_json.get("random_key")

        return ChatResponse(
            message=text_explanation,
            base_random_keys=[winning_key] if winning_key else []
        )
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Could not parse final LLM comparison response: {e}")
        # If parsing fails, return the full raw text as a fallback.
        return ChatResponse(message=llm_response)