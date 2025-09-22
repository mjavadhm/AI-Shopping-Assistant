from openai import AsyncOpenAI, OpenAI
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.core.logger import logger

total_cost_per_session = 0.0
current_request_cost = 0.0
if settings.OPENAI_API_KEY:
    async_client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE,
    )
    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE,
    )
else:
    async_client = None
    logger.warning("⚠️ OpenAI API key or base URL is not set. LLM service will be disabled.")


async def simple_openai_gpt_request(
    message: str,
    systemprompt: str,
    model: str = 'gpt-4.1-mini',
    chat_history: Optional[List[dict]] = None
) -> str:
    """
    Sends a chat completion request to OpenAI GPT model asynchronously.

    Args:
        message (str): The user's message to send to the model.
        systemprompt (str): The system prompt to guide the model's behavior.
        model (str, optional): The model name to use. Defaults to 'gpt-4o-mini'.
        chat_history (Optional[List[dict]], optional): Previous chat history messages. Defaults to None.

    Returns:
        string: (response_content) where response_content is the model's reply.

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

        response = await async_client.chat.completions.create(
            model=model,
            messages=messages,
        )
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = calculate_gpt_cost(input_tokens, output_tokens, model = model)
        logger.info(f"--------------------------\nmodel: {model}\ncost:{cost}\n--------------------------")
        # input_tokens = response.usage.prompt_tokens
        # output_tokens = response.usage.completion_tokens

        return response.choices[0].message.content
    except Exception as e:
        logger.error(e)
        raise

async def simple_openai_gpt_request_with_tools(
    message: str,
    systemprompt: str,
    tools: List[Dict[str, Any]],
    model: str = 'gpt-4o-mini',
    chat_history: Optional[List[dict]] = None,
    tools_answer=None
):
    """
    Sends a chat completion request with tools to OpenAI GPT model asynchronously.

    Args:
        message (str): The user's message to send to the model.
        systemprompt (str): The system prompt to guide the model's behavior.
        tools (List[Dict[str, Any]]): List of tools available to the model.
        model (str, optional): The model name to use. Defaults to 'gpt-4o-mini'.
        chat_history (Optional[List[dict]], optional): Previous chat history messages. Defaults to None.

    Returns:
        Dict[str, Any]: Dictionary containing:
            - content: The model's text response (if any)
            - tool_calls: List of tool calls made by the model (if any)
            - finish_reason: The reason the model stopped generating

    Raises:
        Exception: If the request fails or an error occurs.
    """
    if not async_client:
        raise Exception("OpenAI async_client is not initialized. Please check your API key and base URL.")
    
    try:
        messages = []
        if systemprompt:
            messages.append({"role": "system", "content": systemprompt})
        if chat_history:
            messages += chat_history
        if message:
            messages.append({"role": "user", "content": message})
        if tools_answer:
            messages += tools_answer
        
        logger.info(f"--> Sending payload to LLM: {messages}")
        
        response = await async_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        logger.info(f"Token usage - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}")
                
        result = response.choices[0].message.content
        
        tool_calls = response.choices[0].message.tool_calls
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = calculate_gpt_cost(input_tokens, output_tokens, model = model)
        logger.info(f"--------------------------\nmodel: {model}\ncost:{cost}\n--------------------------")
        return result, tool_calls
        
    except Exception as e:
        logger.error(f"Error in simple_openai_gpt_request_with_tools: {e}")
        raise
    
async def analyze_image(user_message, base64_image, prompt, model="gpt-4.1"):
    try:

        system_message = {"role": "system", "content": prompt}
        
        current_message = [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": user_message},
                {
                    "type": "input_image",
                    "image_url": base64_image,
                },
            ],
        }]
        
        # Combine history messages with the current message
        all_messages = [system_message] + current_message
        logger.info(str(all_messages))
        response = await async_client.chat.completions.create(
            model=model,
            messages=all_messages
        )
        description = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens if hasattr(response, 'usage') else 0
        output_tokens = response.usage.completion_tokens if hasattr(response, 'usage') else 0
        input_tokens, output_tokens, cost = await calculate_gpt_cost(int(input_tokens), int(output_tokens), 'gpt-4o')        
        logger.info(f"--------------------------\nmodel: {model}\ncost:{cost}\n--------------------------")
        return description
    
    except Exception as e:
        logger.error(e)
    
def get_embeddings(texts, model="text-embedding-3-small", dimensions=512):
    response = client.embeddings.create(
        input=texts,
        model=model,
        dimensions=dimensions
    )
    return [embedding.embedding for embedding in response.data]


def calculate_gpt_cost(input_tokens, output_tokens, model = 'gpt-4o-mini'):
    try:
        global total_cost_per_session, current_request_cost
        if model == 'gpt-4o':
            input_token_cost_per_million = 2.5
            output_token_cost_per_million = 10
        if model == 'gpt-4o-mini':
            input_token_cost_per_million = 0.150
            output_token_cost_per_million = 0.600
        if model == 'gpt-4.1-mini':
            input_token_cost_per_million = 0.40
            output_token_cost_per_million = 1.60
        if model == 'gpt-4.1-nano':
            input_token_cost_per_million = 0.1
            output_token_cost_per_million = 0.4
        if model == 'gpt-4.1':
            input_token_cost_per_million = 2.00
            output_token_cost_per_million = 8.00
        if model == 'gpt-5':
            input_token_cost_per_million = 1.25
            output_token_cost_per_million = 10.00
        if model == 'gpt-5-mini':
            input_token_cost_per_million = 0.25
            output_token_cost_per_million = 2.00
        if model == 'gpt-5-nano':
            input_token_cost_per_million = 0.05
            output_token_cost_per_million = 0.40
            
        
        input_cost = (input_tokens / 1_000_000) * input_token_cost_per_million
        
        output_cost = (output_tokens / 1_000_000) * output_token_cost_per_million
        
        total_cost = input_cost + output_cost
        total_cost_per_session += total_cost
        current_request_cost += total_cost
        
        return input_tokens, output_tokens, total_cost
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise
