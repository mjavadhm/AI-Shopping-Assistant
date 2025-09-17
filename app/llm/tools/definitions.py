search_products_tool = {
    "type": "function",
    "function": {
        "name": "search_products_by_keywords",
        "description": "Searches the product database based on a list of keywords from the user's query. Use this to find the product the user is asking for.",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of essential keywords from the user's request. e.g., ['فلاور بگ', 'رز سفید']"
                }
            },
            "required": ["keywords"],
        },
    },
}

FIRST_SCENARIO_TOOLS = [
    search_products_tool,
]