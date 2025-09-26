import json
import aiohttp
from fastapi import HTTPException
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository
from app.core.logger import logger
from app.llm.prompts import SELECT_BEST_MATCH_PROMPT
from app.services.openai_service import simple_openai_gpt_request_with_tools
from app.llm.tools.definitions import EMBED_FIRST_AGENT_TOOLS, EMBED_FIRST_SCENARIO_TOOLS


class Utils:
    async def post_async_request(url: str, payload: dict) -> Any:
        """
        Makes an asynchronous POST request to the specified URL with the given payload.

        Args:
            url: The endpoint URL to send the POST request to.
            payload: The JSON-serializable dictionary to include in the request body.

        Returns:
            The JSON-decoded response from the server.

        Raises:
            HTTPException: If the request fails or the response is invalid.
        """

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Request to {url} failed with status {response.status}")
                        raise HTTPException(status_code=response.status, detail="Failed to get a valid response from the server.")
                    return await response.json()
        except Exception as e:
            logger.error(f"Error during POST request to {url}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error during external request.")
    @staticmethod    
    async def find_exact_product_name_service(user_message: str, db: AsyncSession, possible_product_name: str) -> Optional[str]:
        if possible_product_name:
            product_names = await repository.find_similar_products(
                db=db,
                product_name=possible_product_name,
            )
        else:
            product_names = "use function to search"
        system_prompt = SELECT_BEST_MATCH_PROMPT.get("new_main_prompt_template_embed", "").format(
            user_query = user_message,
            search_results_str=str(product_names)
        )
        llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
            message="",
            systemprompt=system_prompt,
            model="gpt-4.1-mini",
            tools=EMBED_FIRST_SCENARIO_TOOLS
        )
        tools_answer = []
        for _ in range(5):
            if tool_calls: 
                for tool_call in tool_calls:
                    function_arguments = tool_call.function.arguments
                    function_name = tool_call.function.name
                    parsed_arguments = json.loads(function_arguments)
                    logger.info(f"function_name = {function_name}\nfunction_arguments: {str(function_arguments)}")
                    possible_product_name = parsed_arguments.get("product_name")
                    product_names = await repository.find_similar_products(db, possible_product_name)
                    tools_answer.append({"role": "assistant", "tool_calls": [{"id": tool_call.id, "type": "function", "function": {"name": function_name, "arguments": function_arguments}}]})
                    tools_answer.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(product_names)})
                llm_response, tool_calls = await simple_openai_gpt_request_with_tools(
                    message=user_message,
                    systemprompt=system_prompt,
                    model="gpt-4.1-mini",
                    tools=EMBED_FIRST_AGENT_TOOLS,
                    tools_answer=tools_answer
                )
            else:
                break
        
        logger.info(f"llm_response: {llm_response}")
        found_key = llm_response.split('\n')[0]
        found_key = found_key.strip()
        logger.info(f"found_key:{found_key}")
        return found_key

    @staticmethod
    async def get_sellers_context_by_key(db: AsyncSession, product_key: str) -> List[Dict[str, Any]]:
        """
        Retrieves and compiles a list of seller details for a given product key.

        This function fetches the product's members (listings), their associated shops,
        and city information, then formats it into a structured list of dictionaries
        for further processing (e.g., by an LLM).

        Args:
            db: The async database session.
            product_key: The unique 'random_key' of the product.

        Returns:
            A list of dictionaries, where each dictionary represents a seller
            with keys like 'price', 'city', 'shop_score', and 'has_warranty'.

        Raises:
            HTTPException: If the product, its members, or seller details cannot be found.
        """
        logger.info(f"Fetching seller context for product_key: {product_key}")

        # Step 1: Find the product to get its member keys
        product = await repository.get_product_by_random_key(db, product_key)
        if not product or not product.members:
            logger.warning(f"No members (sellers) found for product_key: {product_key}")
            raise HTTPException(status_code=404, detail=f"No sellers found for product: {product_key}")

        # Step 2: Fetch the member objects from the keys
        member_objects = await repository.get_members_by_keys(db, product.members)
        if not member_objects:
            logger.warning(f"Could not find member details for product_key: {product_key}")
            raise HTTPException(status_code=404, detail=f"Seller details could not be found for product: {product_key}")

        # Step 3: Fetch shop details in a single batch query to avoid N+1 problem
        shop_ids = list(set(member.shop_id for member in member_objects))
        shops_with_details = await repository.get_shops_with_details_by_ids(db, shop_ids)
        shop_details_map = {shop.id: shop for shop in shops_with_details}

        # Step 4: Compile the final context list
        sellers_context = []
        for member in member_objects:
            shop_info = shop_details_map.get(member.shop_id)
            if shop_info and shop_info.city:
                sellers_context.append({
                    "price": member.price,
                    "city": shop_info.city.name,
                    "shop_score": shop_info.score,
                    "has_warranty": shop_info.has_warranty
                })

        if not sellers_context:
            logger.error(f"Failed to construct complete seller details for product: {product_key}")
            raise HTTPException(status_code=404, detail=f"Could not construct seller details for product: {product_key}")

        logger.info(f"Successfully compiled seller context for {len(sellers_context)} sellers.")
        return sellers_context

    @staticmethod
    def execute_generated_code(code: str, data: list) -> Any:
        """
        Executes the LLM-generated Python code in a restricted scope.
        """
        try:
            local_scope = {}
            exec(code, globals(), local_scope)
            
            calculator_func = local_scope.get('calculate')

            if not callable(calculator_func):
                logger.error("'calculate' function not found or not callable in LLM-generated code.")
                raise ValueError("Invalid code generated by the model.")

            return calculator_func(data)

        except Exception as e:
            logger.error(f"Error executing generated code: {e}", exc_info=True)
            # This error can be re-raised and caught by the main handler's try-except block
            raise
        

    @staticmethod
    def parse_llm_json_response(response_str: str) -> Dict[str, Any]:
        """
        Parses a JSON object from an LLM's string response.

        This function robustly handles cases where the JSON is embedded within
        markdown code fences (```json ... ```) or is just a raw string.

        Args:
            response_str: The string response from the Language Model.

        Returns:
            A dictionary parsed from the JSON string. Returns an empty dictionary
            if parsing fails.
        """
        try:
            # Check if the response is wrapped in markdown fences
            if "```json" in response_str:
                json_part = response_str.split("```json")[1].split("```")[0].strip()
                return json.loads(json_part)
            else:
                # If no fences, assume the whole string is the JSON
                return json.loads(response_str.strip())
        except (json.JSONDecodeError, IndexError) as e:
            # logger.error(f"Failed to parse JSON from LLM response: {e}") # You can add logging here
            print(f"Error parsing JSON from LLM response: {e}") # Or just print
            return {}