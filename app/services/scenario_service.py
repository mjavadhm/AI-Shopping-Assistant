from app.schemas.chat import ChatRequest, ChatResponse
from app.services.openai_service import simple_openai_gpt_request
from app.llm.prompts import SCENARIO_ONE_PROMPTS
from app.core.logger import logger


async def check_scenario_one(request: ChatRequest) -> ChatResponse:
    """
    Check if the request matches Scenario One and process it accordingly.

    Args:
        request (ChatRequest): The incoming chat request.
    Returns:
        ChatResponse: The response for Scenario One or None if not matched.
    """
    try:
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
            # if request.chat_id == "scenario-one":
            response = await scenario_one(request)
            
        return response
    except Exception as e:
        logger.error(e,exc_info=True)

async def scenario_one(request: ChatRequest) -> ChatResponse:
    system_prompt = SCENARIO_ONE_PROMPTS.get("system", "")
    user_message = request.messages[-1].content.strip()

    llm_response = await simple_openai_gpt_request(
        message=user_message,
        systemprompt=system_prompt,
        model="gpt-4.1-mini"
    )

    return ChatResponse(message=llm_response)