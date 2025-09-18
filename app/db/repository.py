from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from . import models
from sqlalchemy import and_
from sqlalchemy.orm import joinedload
from sqlalchemy.dialects.postgresql import to_tsquery

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
async def search_products_by_keywords(
    db: AsyncSession, 
    essential_keywords: List[str], 
    descriptive_keywords: Optional[List[str]] = None
) -> Optional[List[str]]:
    """
    Performs a hybrid search using essential (AND) and descriptive (OR) keywords.
    """
    if not essential_keywords:
        return None

    # Helper function to process keywords
    def process_and_join(keywords: List[str], operator: str) -> str:
        processed = []
        for keyword in keywords:
            processed.extend(keyword.split())
        return f" {operator} ".join(processed)

    # Build the essential part of the query (using AND)
    essential_query_part = process_and_join(essential_keywords, '&')
    final_query_str = f"({essential_query_part})"

    # If there are descriptive keywords, build that part (using OR) and append it
    if descriptive_keywords:
        descriptive_query_part = process_and_join(descriptive_keywords, '|')
        final_query_str += f" & ({descriptive_query_part})"

    # Execute the final hybrid query
    query = select(models.BaseProduct.persian_name).where(
        models.BaseProduct.persian_name_tsv.op('@@')(to_tsquery('simple', final_query_str))
    )
    
    result = await db.execute(query)
    product_names = result.scalars().all()
    
    return product_names if product_names else None

# async def search_products_by_keywords(db: AsyncSession, keywords: List[str]) -> Optional[List[str]]:
#     """
#     Asynchronously searches for products by a list of keywords in their Persian name.
#     It returns a list of product names that contain ALL of the specified keywords.
#     """
#     if not keywords:
#         return None

#     # We create a list of `ilike` conditions to perform a case-insensitive "contains" search.
#     # The `and_` ensures that the product name must contain ALL keywords.
#     conditions = and_(*[models.BaseProduct.persian_name.ilike(f"%{keyword}%") for keyword in keywords])
    
#     query = select(models.BaseProduct.persian_name).where(conditions)
    
#     result = await db.execute(query)
#     product_names = result.scalars().all()
    
#     return product_names if product_names else None

async def get_product_features_by_name(db: AsyncSession, product_name: str) -> Optional[dict]:
    
    query = select(models.BaseProduct.extra_features).where(
        models.BaseProduct.persian_name == product_name
    )
    result = await db.execute(query)
    features = result.scalar_one_or_none()
    return features if features else None

async def get_product_by_name_like(db: AsyncSession, product_name: str) -> Optional[models.BaseProduct]:
    query = select(models.BaseProduct).where(
        models.BaseProduct.persian_name.contains(product_name)
    )
    
    result = await db.execute(query)
    
    product = result.scalars().first()
    
    return product

async def get_product_by_random_key(db: AsyncSession, random_key: str) -> Optional[models.BaseProduct]:
    
    query = select(models.BaseProduct).where(
        models.BaseProduct.random_key == random_key
    )
    
    result = await db.execute(query)
    
    product = result.scalar_one_or_none()
    
    return product


# async def get_product_with_seller_details(db: AsyncSession, base_random_key: str):
#     """
#     Fetches a product and all its related seller details (members, shops, cities)
#     in a single, optimized query to avoid the N+1 problem.
#     """
#     query = (
#         select(models.BaseProduct)
#         .where(models.BaseProduct.base_random_key == base_random_key)
#         .options(
#             joinedload(models.BaseProduct.members)
#             .joinedload(models.Member.shop)
#             .joinedload(models.Shop.city)
#         )
#     )
    
#     result = await db.execute(query)
#     # unique() is important to get distinct product results
#     product = result.unique().scalar_one_or_none()
    
#     return product

async def get_members_by_keys(db: AsyncSession, member_keys: list[str]):
    """
    Fetches a list of Member objects based on a list of their random_keys.
    """
    if not member_keys:
        return []
    
    query = select(models.Member).where(models.Member.random_key.in_(member_keys))
    result = await db.execute(query)
    return result.scalars().all()

# This function is also still needed
async def get_shops_with_details_by_ids(db: AsyncSession, shop_ids: list[int]):
    """
    Fetches a list of shops and their related cities using a single optimized query.
    """
    if not shop_ids:
        return []
        
    query = (
        select(models.Shop)
        .where(models.Shop.id.in_(shop_ids))
        .options(joinedload(models.Shop.city))
    )
    result = await db.execute(query)
    return result.scalars().all()