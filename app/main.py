from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession


from .schemas.chat import ChatRequest, ChatResponse
from .core.logger import logger
from .llm.prompts import SCENARIO_ONE_PROMPTS
from .services.scenario_service import check_scenario_one
from .db.session import get_db 
app = FastAPI()

@app.get("/")
def read_root():
    """A simple endpoint to check if the server is running."""
    logger.info("Root endpoint was called")
    return {"Hello": "World"}

@app.post("/chat", response_model=ChatResponse)
async def chat_handler(
    request: ChatRequest, 
    db: AsyncSession = Depends(get_db) # <--- Inject the DB session here
):
    """
    This endpoint handles the chat requests and implements the logic for different scenarios.
    """
    logger.info(f"Received chat request with chat_id: {request.chat_id}")
    logger.info(f"--> INCOMING Request Body: {request.model_dump()}")

    response = await check_scenario_one(request, db=db)        
    logger.info(f"Sending response for chat_id: {request.chat_id}")
    logger.debug(f"Response body: {response.model_dump()}")
    
    return response