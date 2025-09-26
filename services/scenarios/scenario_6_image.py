from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.schemas.chat import ChatRequest, ChatResponse
from app.core.logger import logger
from app.services.openai_service import analyze_image, simple_openai_gpt_request
from app.llm.prompts import SCENARIO_SIX_PROMPTS
from utils import Utils




async def handle(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    """
    Handles Scenario 6: Image Object Detection.

    The user has uploaded an image and potentially a text query. This function
    extracts the image data, sends it to a embedding model for analysis, and
    returns the identified object's name.

    Args:
        request: The incoming chat request object, containing messages of type 'image' and 'text'.
        db: The async database session (not used in this scenario but required by the handler signature).

    Returns:
        A ChatResponse object containing the name of the object identified in the image.
    """
    logger.info("Handling Scenario 6: Image Object Detection.")
    base64_image = ""

    # Extract image content from messages
    for message in request.messages:
        if message.type == "image":
            base64_image = message.content
        if message.type == "text":
            text_message = message.content

    if not base64_image:
        raise HTTPException(status_code=400, detail="Image content not found in the request.")



    payload = {"base64_image": base64_image}
    
    url = "https://image-embed-server.darkube.app/search/"

    logger.info(f"Sending image to embedding server at {url}")
    search_results = await Utils.post_async_request(url=url, payload=payload)

    if not search_results or not isinstance(search_results, list) or len(search_results) == 0:
        logger.error("No valid response from the image search server.")
        raise HTTPException(status_code=500, detail="Could not find a match for the image.")

    try:
        first_result_id = search_results[0].get("id")
        if not first_result_id:
            raise KeyError("'id' not found in the first result")
            
    except (KeyError, IndexError) as e:
        logger.error(f"Error parsing response from image search server: {e}")
        raise HTTPException(status_code=500, detail="Invalid response format from the image search server.")
    
    logger.info(f"Found product key from image search: {first_result_id}")

    system_prompt = SCENARIO_SIX_PROMPTS.get("route")
    llm_response = await simple_openai_gpt_request(
                message=text_message,
                systemprompt=system_prompt,
                model="gpt-4.1-nano",
                        
            )
    if "name" in llm_response.lower():
        return ChatResponse(message=search_results[0].get("persian_name"))
    else:
        return ChatResponse(base_random_keys=[first_result_id])