from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from . import models

async def search_product_by_name(db: AsyncSession, product_name: str) -> Optional[List[str]]:
    """
    Asynchronously searches for products by their Persian name in the database.

    This function performs a case-insensitive search to find products whose
    Persian name contains the given search term.

    Args:
        db: The SQLAlchemy AsyncSession to use for the query.
        product_name: The search term to look for in the product names.

    Returns:
        A list of 'random_key' strings for the matching products,
        or None if no products are found.
    """
    query = select(models.BaseProduct.random_key).where(
        models.BaseProduct.persian_name == product_name
    )
    
    result = await db.execute(query)
    
    # .scalars() retrieves the first column of each row, which is the random_key.
    keys = result.scalars().all()
    
    if keys:
        return keys
        
    return None