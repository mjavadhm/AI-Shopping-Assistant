from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from . import models
from sqlalchemy import and_

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

async def search_products_by_keywords(db: AsyncSession, keywords: List[str]) -> Optional[List[str]]:
    """
    Asynchronously searches for products by a list of keywords in their Persian name.
    It returns a list of product names that contain ALL of the specified keywords.
    """
    if not keywords:
        return None

    # We create a list of `ilike` conditions to perform a case-insensitive "contains" search.
    # The `and_` ensures that the product name must contain ALL keywords.
    conditions = and_(*[models.BaseProduct.persian_name.ilike(f"%{keyword}%") for keyword in keywords])
    
    query = select(models.BaseProduct.persian_name).where(conditions)
    
    result = await db.execute(query)
    product_names = result.scalars().all()
    
    return product_names if product_names else None

async def get_product_features_by_name(db: AsyncSession, product_name: str) -> Optional[dict]:
    
    query = select(models.BaseProduct.extra_features).where(
        models.BaseProduct.persian_name == product_name
    )
    result = await db.execute(query)
    features = result.scalar_one_or_none()
    return features if features else None

async def get_product_by_random_key(db: AsyncSession, random_key: str) -> Optional[models.BaseProduct]:
    
    query = select(models.BaseProduct).where(
        models.BaseProduct.random_key == random_key
    )
    
    result = await db.execute(query)
    
    product = result.scalar_one_or_none()
    
    return product