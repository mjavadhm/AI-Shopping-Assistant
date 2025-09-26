from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.chat import ChatRequest, ChatResponse
from app.core.logger import logger

async def handle(request: ChatRequest, db: AsyncSession, found_key: str) -> ChatResponse:
    """
    Handles Scenario 1: Direct Product Search.

    This is just for better code organization.

    The user has provided a specific product name, and the router has already
    identified the unique product key. This function's sole responsibility
    is to return that key in the correct response format.

    Args:
        request: The incoming chat request object.
        db: The async database session.
        found_key: The unique 'random_key' of the product that was
                   identified by the scenario_router.

    Returns:
        A ChatResponse object containing the base_random_key of the found product.
    """
    logger.info(f"Handling Scenario 1: Direct Search. Returning key: {found_key}")

    if not found_key:
        logger.warning("Scenario 1 handler called without a found_key.")
        return ChatResponse(message="I couldn't identify the specific product you're looking for.")

    return ChatResponse(base_random_keys=[found_key])