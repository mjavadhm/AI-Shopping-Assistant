import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import repository
from app.core.logger import logger


async def search_products_by_keywords(db: AsyncSession, keywords: list[str]) -> str:
    """
    The actual implementation for the search_products_by_keywords tool.
    It queries the database and returns a JSON string of the results.
    """
    logger.info(f"Executing tool `search_products_by_keywords` with: {keywords}")
    
    if not keywords:
        return "Cannot search with empty keywords. Ask the user for more details."

    search_results = await repository.search_products_by_keywords(db=db, keywords=keywords)
    
    if not search_results:
        return json.dumps({"status": "not_found", "message": "No products found matching the keywords."})
    
    if len(search_results) > 50:
         return json.dumps({"status": "too_many_results", "count": len(search_results)})

    # Return the results as a JSON string, which is a standard practice.
    return json.dumps({"status": "success", "results": search_results}, ensure_ascii=False)
