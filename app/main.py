from fastapi import FastAPI
from .schemas.chat import ChatRequest, ChatResponse
from .core.logger import logger
from .llm.prompts import SCENARIO_ONE_PROMPTS
app = FastAPI()

@app.get("/")
def read_root():
    """A simple endpoint to check if the server is running."""
    logger.info("Root endpoint was called")
    return {"Hello": "World"}

@app.post("/chat", response_model=ChatResponse)
async def chat_handler(request: ChatRequest):
    """
    This endpoint handles the chat requests and implements the logic for different scenarios.
    """
    logger.info(f"Received chat request with chat_id: {request.chat_id}")
    logger.debug(f"Request body: {request.model_dump()}")

    last_message = request.messages[-1].content.strip()
    response = None

    # --- Scenario Zero: Sanity Checks ---
    if request.chat_id == "sanity-check-ping" and last_message == "ping":
        response = ChatResponse(message="pong")

    elif request.chat_id == "sanity-check-base-key" and last_message.startswith("return base random key:"):
        key = last_message.replace("return base random key:", "").strip()
        response = ChatResponse(base_random_keys=[key])

    elif request.chat_id == "sanity-check-member-key" and last_message.startswith("return member random key:"):
        key = last_message.replace("return member random key:", "").strip()
        response = ChatResponse(member_random_keys=[key])

    else:
        
    logger.info(f"Sending response for chat_id: {request.chat_id}")
    logger.debug(f"Response body: {response.model_dump()}")
    
    return response