import json
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.schemas.chat import ChatRequest, ChatResponse
from app.core.logger import logger
from app.services.openai_service import simple_openai_gpt_request
from app.llm.prompts import SCENARIO_THREE_PROMPTS
from utils import Utils

async def handle(request: ChatRequest, db: AsyncSession, found_key: str) -> ChatResponse:
    """
    Handles Scenario 3: Seller Information.

    The user is asking a question about the sellers of a product (e.g., price,
    warranty, location). This function gathers seller data, uses an LLM to
    generate Python code to answer the question, executes that code, and
    returns the result.

    Args:
        request: The incoming chat request object.
        db: The async database session.
        found_key: The unique 'random_key' of the product identified by the router.

    Returns:
        A ChatResponse object containing the calculated answer to the user's question.
    """
    logger.info(f"Handling Scenario 3: Seller Info for key: {found_key}")
    user_message = request.messages[-1].content.strip()

    try:
        # Step 1: Get seller data using the utility function
        sellers_context = await Utils.get_sellers_context_by_key(db, found_key)
        context_str = json.dumps(sellers_context, ensure_ascii=False, indent=2)

        # Step 2: Prepare prompt for the LLM to generate Python code
        prompt_template = SCENARIO_THREE_PROMPTS.get("calculate_prompt")
        if not prompt_template:
            logger.error("Calculate prompt for Scenario 3 is missing.")
            raise HTTPException(status_code=500, detail="Internal server error: Missing prompt configuration.")

        code_generation_prompt = prompt_template.format(
            user_message=user_message,
            context_str=context_str
        )

        # Step 3: Call LLM to generate the code
        llm_response_code = await simple_openai_gpt_request(
            message='',
            systemprompt=code_generation_prompt,
            model="gpt-4.1",
        )

        # Extract Python code from markdown block if present
        if "```python" in llm_response_code:
            llm_response_code = llm_response_code.split("```python")[1].split("```")[0].strip()

        logger.info(f"LLM generated the following Python code:\n{llm_response_code}")

        # Step 4: Execute the generated code safely
        final_answer = utils.execute_generated_code(llm_response_code, sellers_context)
        logger.info(f"Calculated result from dynamic code: {final_answer}")

        return ChatResponse(message=str(final_answer))

    except HTTPException as http_exc:
        # Re-raise known HTTP exceptions
        raise http_exc
    except Exception as e:
        # Catch other unexpected errors
        logger.error(f"An unexpected error occurred in Scenario 3 handler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your request.")


