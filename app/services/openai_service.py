from openai import AsyncOpenAI
from typing import Optional, List

from app.core.config import settings
from app.core.logger import logger

if settings.OPENAI_API_KEY:
    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE,
    )
else:
    client = None
    logger.warning("⚠️ OpenAI API key or base URL is not set. LLM service will be disabled.")


async def simple_openai_gpt_request(
    message: str,
    systemprompt: str,
    model: str = 'gpt-4.1-mini',
    chat_history: Optional[List[dict]] = None
) -> tuple:
    """
    Sends a chat completion request to OpenAI GPT model asynchronously.

    Args:
        message (str): The user's message to send to the model.
        systemprompt (str): The system prompt to guide the model's behavior.
        model (str, optional): The model name to use. Defaults to 'gpt-4o-mini'.
        chat_history (Optional[List[dict]], optional): Previous chat history messages. Defaults to None.

    Returns:
        tuple: (response_content) where response_content is the model's reply.

    Raises:
        Exception: If the request fails or an error occurs.
    """
    try:
        messages = []
        if systemprompt:
            messages.append({"role": "system", "content": systemprompt})
        if chat_history:
            messages += chat_history
        if message:
            messages.append({"role": "user", "content": message})

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
        )

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        return response.choices[0].message.content
    except Exception as e:
        logger.error(e)
        raise
