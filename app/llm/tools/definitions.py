search_products_tool = {
    "type": "function",
    "function": {
        "name": "search_products_by_keywords",
        "description": "Searches the product database based on essential and descriptive keywords from the user's query.",
        "parameters": {
            "type": "object",
            "properties": {
                "essential_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of core keywords that DEFINE the product. e.g., ['فلاور بگ', 'گوشی', 'سامسونگ']."
                },
                "descriptive_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of optional, descriptive keywords that DESCRIBE the product's features. e.g., ['رز سفید', 'آفتابگردان', 'مشکی', '256 گیگ']."
                }
            },
            "required": ["essential_keywords"],
        },
    },
}


get_feature_tool = {
    "type": "function",
    "function": {
        "name": "get_product_feature",
        "description": "یک ویژگی خاص (مانند عرض، وزن، سایز و...) را برای یک محصول مشخص بازیابی می‌کند.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "نام کامل و دقیق محصول. مثال: 'پارچه تریکو جودون 1/30 لاکرا گردباف نوریس به رنگ زرد طلایی'"
                },
                "feature_name": {
                    "type": "string",
                    "description": "ویژگی خاصی که کاربر به دنبال آن است. مثال: 'عرض'"
                }
            },
            "required": ["product_name", "feature_name"],
        },
    },
}

FIRST_SCENARIO_TOOLS = [
    search_products_tool,
]

SECOND_SCENARIO_TOOLS = [
    get_feature_tool,
]