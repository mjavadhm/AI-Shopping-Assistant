import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger
from . import functions as tool_functions

class ToolHandler:
    """
    A centralized handler to manage and execute available tools.
    It maps tool names to their actual Python functions.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self._tool_map = {
            "search_products_by_keywords": tool_functions.search_products_by_keywords,
     
        }

    async def handle_tool_call(self, tool_calls, tools_answer) -> dict | None:
        """
        Executes a tool call requested by the LLM.

        Args:
            tool_call: The tool_call object from the OpenAI response.

        Returns:
            A dictionary formatted for the OpenAI messages API, 
            containing the tool's response.
        """

        for tool_call in tool_calls:
            function_arguments = tool_call.function.arguments
            function_name = tool_call.function.name
            if function_name not in self._tool_map:
                logger.warning(f"Unknown tool called: {function_name}")
            
                return None

            # Get the actual function to call from our map
            function_to_call = self._tool_map[function_name]
            
            # Parse the arguments provided by the LLM
            try:
                function_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse arguments for tool {function_name}")
                return None
            
            # Call the function with its arguments and the db session
            # **function_args unpacks the dictionary into keyword arguments (e.g., keywords=...)
            tool_output = await function_to_call(db=self.db, **function_args)
            tools_answer.append({"role": "assistant", "function_call": {"name": function_name, "arguments": function_arguments}})
            tools_answer.append({"role": "function", "name": function_name, "content": tool_output})
        return tools_answer
        