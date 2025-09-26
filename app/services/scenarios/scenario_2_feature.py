from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.schemas.chat import ChatRequest, ChatResponse
from app.core.logger import logger
from app.db import repository
from app.services.openai_service import simple_openai_gpt_request
from app.llm.prompts import SCENARIO_TWO_PROMPTS

async def handle(request: ChatRequest, db: AsyncSession, found_key: str) -> ChatResponse:
    """
    Handles Scenario 2: Feature Extraction.

    The user is asking for a specific attribute of a known product. This function
    retrieves the product's features from the database and uses an LLM to
    formulate a natural language answer to the user's question.

    Args:
        request: The incoming chat request object.
        db: The async database session.
        found_key: The unique 'random_key' of the product identified by the router.

    Returns:
        A ChatResponse object containing a message with the requested feature's value.
    """
    logger.info(f"Handling Scenario 2: Feature Extraction for key: {found_key}")
    user_message = request.messages[-1].content.strip()

    try:
        # Step 1: Retrieve the product from the database
        product = await repository.get_product_by_random_key(db, found_key)

        if not product:
            logger.warning(f"Product with key '{found_key}' not found in the database for Scenario 2.")
            # Although the router should prevent this, it's good practice to handle it.
            raise HTTPException(status_code=404, detail=f"Product with key {found_key} not found.")

        # Step 2: Prepare the context and prompt for the LLM
        # The context includes both the user's question and the product's available features.
        message_for_llm = f"user input:{user_message}\n\nproduct_features:{str(product.extra_features)}"
        system_prompt = SCENARIO_TWO_PROMPTS.get("main_prompt_step_2", "")

        if not system_prompt:
            logger.error("System prompt for Scenario 2 is missing.")
            raise HTTPException(status_code=500, detail="Internal server error: Missing prompt configuration.")

        # Step 3: Call the LLM to get a user-friendly answer
        llm_response = await simple_openai_gpt_request(
            message=message_for_llm,
            systemprompt=system_prompt,
            model="gpt-4.1",
        )

        logger.info(f"LLM response for feature extraction: {llm_response}")
        return ChatResponse(message=llm_response)

    except HTTPException as http_exc:
        # Re-raise HTTP exceptions to be handled by FastAPI's exception handling
        raise http_exc
    except Exception as e:
        # Catch any other unexpected errors (e.g., database connection issues, LLM API errors)
        logger.error(f"An unexpected error occurred in Scenario 2 handler: {e}", exc_info=True)
        # Return a generic error message to the user
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your request.")