import json
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.db import repository
from app.core.logger import logger


async def search_products_by_keywords(
    db: AsyncSession, 
    essential_keywords: List[str], 
    descriptive_keywords: Optional[List[str]] = None
) -> str:
    """
    The implementation for the search_products_by_keywords tool.
    It calls the repository function with the new structured keywords.
    """
    logger.info(f"Executing tool `search_products_by_keywords` with: essential={essential_keywords}, descriptive={descriptive_keywords}")
    
    if not essential_keywords:
        return json.dumps({"status": "error", "message": "Cannot search without essential keywords."})

    # Call the repository function with the exact same arguments
    search_results = await repository.search_products_by_keywords(
        db=db, 
        essential_keywords=essential_keywords,
        descriptive_keywords=descriptive_keywords
    )
    
    if not search_results:
        return json.dumps({"status": "not_found", "message": """No products found matching the keywords.\nYour keywords were too specific. You MUST try again.\nCall the tool again, but this time **remove one keyword** from your `descriptive_keywords`.\nContinue this process of removing descriptive keywords one by one until you get a result. If all descriptive keywords are removed and you still get "not_found", start removing from `essential_keywords`."""})
    
    if len(search_results) > 100:
         return json.dumps({"status": "too_many_results\nThe search is too general. You need to make it more specific.\nYou MUST call the tool again, this time **adding one more specific keyword** from the user's original query to your search.", "count": len(search_results)})

    # Return the results as a JSON string
    return json.dumps({"status": "success", "results": search_results}, ensure_ascii=False)



# async def search_products_by_keywords(db: AsyncSession, keywords: list[str]) -> str:
#     """
#     The actual implementation for the search_products_by_keywords tool.
#     It queries the database and returns a JSON string of the results.
#     """
#     logger.info(f"Executing tool `search_products_by_keywords` with: {keywords}")
    
#     if not keywords:
#         return "Cannot search with empty keywords. Ask the user for more details."

#     search_results = await repository.search_products_by_keywords(db=db, keywords=keywords)
    
#     if not search_results:
#         return json.dumps({"status": "not_found", "message": "No products found matching the keywords."})
    
#     if len(search_results) > 100:
#          return json.dumps({"status": "too_many_results", "count": len(search_results)})

#     # Return the results as a JSON string, which is a standard practice.
#     return json.dumps({"status": "success", "results": search_results}, ensure_ascii=False)



async def get_product_feature(db: AsyncSession, product_name: str, feature_name: str) -> str:
    logger.info(f"Executing tool `get_product_feature` for product: '{product_name}' and feature: '{feature_name}'")

    features = await repository.get_product_features_by_name(db=db, product_name=product_name)

    if not features:
        return json.dumps({"status": "product_not_found", "message": "محصول مشخص شده پیدا نشد."})


    feature_mapping = {
        "عرض": "width", "width": "width",
        "وزن": "weight", "weight": "weight",
        "سایز": "size", "size": "size",
    }
    
    normalized_feature_name = feature_mapping.get(feature_name.lower())

    if not normalized_feature_name or normalized_feature_name not in features:
        return json.dumps({
            "status": "feature_not_found",
            "message": f"ویژگی '{feature_name}' برای این محصول پیدا نشد.",
            "available_features": features
        })

    feature_value = features[normalized_feature_name]
    return json.dumps({"status": "success", "feature_name": feature_name, "feature_value": feature_value})

