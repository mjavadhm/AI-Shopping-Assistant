search_products_tool = {
    "type": "function",
    "function": {
        "name": "full_text_search_products_by_keywords",
        "description": "Searches the product database based on essential and descriptive keywords from the user's query.",
        "parameters": {
            "type": "object",
            "properties": {
                "essential_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of core keywords that DEFINE the product. e.g., ['فلاور بگ', 'گوشی', 'سامسونگ']. i will use this in full text search with and"
                },
                "descriptive_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of optional, descriptive keywords that DESCRIBE the product's features. e.g., ['رز سفید', 'آفتابگردان', 'مشکی', '256 گیگ'].i will use this in full text search with or"
                }
            },
            "required": ["essential_keywords"],
        },
    },
}
old_search_products_tool = {
    "type": "function",
    "function": {
        "name": "search_products_by_keywords",
        "description": "Searches the product database using a list of atomic and essential keywords. Call this function when the initial search is unsuccessful or the results are incorrect, requiring a more refined set of keywords.",
        "parameters": {
        "type": "object",
        "properties": {
            "keywords": {
            "type": "array",
            "items": {
                "type": "string"
            },
            "description": "A list of the most critical, individual keywords extracted from the query. Rules: Correct typos, remove stop words (like 'مدل'), and separate all terms. Example: For the query 'تلویزیون مدل gt24', the correct value is ['تلویزیون', 'gt24']."
            }
        },
        "required": [
            "keywords"
        ]
        }
    }
    }

extract_search_keywords_tool = {
    "type": "function",
    "function": {
        "name": "full_text_search_products_by_keywords",
        "description": "Extracts and structures keywords from a user's message, preparing them for a product search.",
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
                    "description": "A list of optional, descriptive keywords that DESCRIBE the product's features. e.g., ['رز سفید', 'مشکی']."
                }
            },
            "required": ["essential_keywords"],
        },
    },
}

product_name_keywords_tool = {
    "type": "function",
    "function": {
        "name": "extract_search",
        "description": "semantic search db",
        "parameters": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "the most possible name of the product(include model number, color, size, etc)."
                }
            },
            "required": ["product_name"]
        }
    }
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
                
            },
            "required": ["product_name"],
        },
    },
}
classify_request_tool = {
    "type": "function",
    "function": {
        "name": "classify_user_request",
        "description": "Classifies the user's request into a scenario",
        "parameters": {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "description": "The classified scenario name (e.g., 'SCENARIO_1_DIRECT_SEARCH')."
                },
            },
            "required": ["scenario"],
        },
    },
}


FIRST_SCENARIO_TOOLS = [
    search_products_tool,
]
OLD_FIRST_SCENARIO_TOOLS = [
    old_search_products_tool,
]

SECOND_SCENARIO_TOOLS = [
    get_feature_tool,
]
FIRST_AGENT_TOOLS = [
    classify_request_tool,
    extract_search_keywords_tool,
]

EMBED_FIRST_AGENT_TOOLS = [
    classify_request_tool,
    product_name_keywords_tool,
]

EMBED_FIRST_SCENARIO_TOOLS = [
    product_name_keywords_tool,
]