from fastapi import FastAPI
from .schemas.chat import ChatRequest, ChatResponse
from .core.logger import logger
from .llm.prompts import SCENARIO_ONE_PROMPTS
from .services.scenario_service import check_scenario_one
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

    response = await check_scenario_one(request)        
    logger.info(f"Sending response for chat_id: {request.chat_id}")
    logger.debug(f"Response body: {response.model_dump()}")
    
    return response