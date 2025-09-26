from fastapi import FastAPI, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
import json
import asyncio

from .schemas.chat import ChatRequest, ChatResponse
from .core.logger import logger
from app.core.json_logger import log_request_response
from .services.scenario_service import check_scenario_one
from .db.session import get_db 
from .services import openai_service
from app.core.context import scenario_context

app = FastAPI()

@app.middleware("http")
async def json_logging_middleware(request: Request, call_next):
    openai_service.current_request_cost = 0.0
    request_body_json = None
    try:
        request_body_bytes = await request.body()
        if request_body_bytes:
            request_body_json = json.loads(request_body_bytes)
        
        async def receive():
            return {"type": "http.request", "body": request_body_bytes}
        request = Request(request.scope, receive)

    except Exception:
        request_body_json = {"error": "Could not parse request body as JSON"}

    response = await call_next(request)

    response_body_json = None
    response_body_bytes = b""
    async for chunk in response.body_iterator:
        response_body_bytes += chunk
    
    try:
        if response_body_bytes:
            response_body_json = json.loads(response_body_bytes)
    except Exception:
        response_body_json = {"error": "Could not parse response body as JSON"}

    scenario = getattr(request.state, "scenario", None)

    log_data = {
        "request": request_body_json,
        "response": response_body_json,
        "openai_cost": openai_service.current_request_cost,
        "scenario": scenario
    }

    task = BackgroundTask(log_request_response, log_data=log_data)

    return Response(
        content=response_body_bytes,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=task,
    )

@app.get("/total-cost")
async def get_total_cost():
    """Returns the total accumulated cost of all OpenAI API calls."""
    return {"total_cost": openai_service.total_cost_per_session}

@app.get("/")
def read_root():
    """A simple endpoint to check if the server is running."""
    logger.info("Root endpoint was called")
    return {"Hello": "World"}

@app.post("/chat", response_model=ChatResponse)
async def chat_handler(
    request: ChatRequest, 
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    This endpoint handles the chat requests and implements the logic for different scenarios.
    """
    logger.info("------------------------------------------------------------------------------------")
    logger.info(f"Received chat request with chat_id: {request.chat_id}")
    logger.info(f"--> INCOMING Request Body: {request.model_dump()}")

    response = await asyncio.wait_for(check_scenario_one(request, db=db, http_request=http_request), timeout=30.0)        
    logger.info(f"Sending response for chat_id: {request.chat_id}")
    logger.info(f"Response body: {response.model_dump()}")
    
    return response