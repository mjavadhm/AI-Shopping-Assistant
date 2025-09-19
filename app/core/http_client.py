import aiohttp
import json
from typing import Dict, Any, Optional
from app.core.logger import logger

async def post_async_request(url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Sends an asynchronous POST request to a specified URL with a JSON payload.

    Args:
        url (str): The target URL for the request.
        payload (Dict[str, Any]): The dictionary to be sent as the JSON body.

    Returns:
        Optional[Dict[str, Any]]: The JSON response from the server as a dictionary, 
                                   or None if an error occurs.
    """
    logger.info(f"Sending async POST request to: {url}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as response:

                response.raise_for_status()
                
                result = await response.json()
                logger.info("✅ Async request successful, response received.")
                return result

        except aiohttp.ClientResponseError as http_err:
            error_body = await response.text()
            logger.error(f"❌ HTTP error occurred: {http_err.status} {http_err.message}")
            logger.error(f"Server response: {error_body}")
            return None
        except aiohttp.ClientError as err:
            logger.error(f"❌ An error occurred during the async request: {err}")
            return None
        except json.JSONDecodeError:
            logger.error("❌ Failed to decode JSON from response.")
            return None