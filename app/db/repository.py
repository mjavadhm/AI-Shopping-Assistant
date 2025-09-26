from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Optional, Any
from . import models
from sqlalchemy import select, func, and_, text, or_, case, literal_column, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import joinedload
from sqlalchemy.dialects.postgresql import to_tsquery
from sqlalchemy.types import Float



async def get_all_sellers_info(db: AsyncSession) -> List[models.Member]:
    """
    Fetches all sellers from the database.
    """
\
async def get_all_categories(db: AsyncSession) -> List[models.Category]:
    """
    Fetches all categories from the database.
    Returns a string where each line is a category title.
    """
    result = await db.execute(select(models.Category.title))
    titles = result.scalars().all()
    return "\n".join(titles)

async def get_category_features_example(db: AsyncSession, category_title: str) -> Optional[dict]:
    """
    Fetches the features_example JSON for a given category title.
    """
    query = select(models.Category.features_example).where(
        models.Category.title == category_title
    )
    result = await db.execute(query)
    features_example = result.scalar_one_or_none()
    return features_example if features_example else None


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

async def find_products_with_aggregated_sellers(
    db: AsyncSession,
    filters_json: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    کالاها را پیدا کرده و فقط آنهایی را برمی‌گرداند که حداقل یک فروشنده منطبق با فیلترها دارند.
    سپس تمام فروشندگان منطبق را در یک فیلد JSON تجمیع می‌کند.
    """
    search_query_text = filters_json.get("search_query")
    structured_filters = filters_json.get("structured_filters", {})

    # ---------- ۱. ساخت یک زیرکوئری (CTE) برای فیلتر کردن فروشندگان ----------
    
    seller_filters = []
    # ... (بخش فیلتر کردن فروشندگان بدون تغییر باقی می‌ماند)
    if "price_min" in structured_filters and structured_filters["price_min"] is not None:
        seller_filters.append(models.Member.price >= structured_filters["price_min"])
    if "price_max" in structured_filters and structured_filters["price_max"] is not None:
        seller_filters.append(models.Member.price <= structured_filters["price_max"])
    if "has_warranty" in structured_filters and structured_filters["has_warranty"]:
        seller_filters.append(models.Shop.has_warranty == True)
    if "city_name" in structured_filters and structured_filters["city_name"]:
        seller_filters.append(models.City.name == structured_filters["city_name"])

    filtered_sellers_cte = (
        select(
            models.Member.base_random_key,
            func.jsonb_build_object(
                'member_key', models.Member.random_key,
                'price', models.Member.price,
                'has_warranty', models.Shop.has_warranty,
                'shop_score', models.Shop.score,
                'city', models.City.name
            ).label("seller_data")
        )
        .join(models.Shop, models.Member.shop_id == models.Shop.id)
        .join(models.City, models.Shop.city_id == models.City.id)
        .where(and_(*seller_filters))
        .cte("filtered_sellers")
    )

    # ---------- ۲. ساخت کوئری اصلی ----------
    
    similarity_score = None
    if search_query_text:
        similarity_score = func.similarity(models.BaseProduct.persian_name, search_query_text)

    query = (
        select(
            models.BaseProduct.persian_name,
            models.BaseProduct.random_key,
            models.BaseProduct.extra_features,
            func.jsonb_agg(filtered_sellers_cte.c.seller_data).label("sellers")
        )
        .join(filtered_sellers_cte, models.BaseProduct.random_key == filtered_sellers_cte.c.base_random_key)
        .group_by(models.BaseProduct.random_key)
    )

    if search_query_text:
        query = query.where(
            models.BaseProduct.persian_name.op("%")(search_query_text),
            similarity_score > 0.1
        ).order_by(similarity_score.desc())
    else:
        query = query.order_by(func.count(filtered_sellers_cte.c.seller_data).desc())

    query = query.limit(10)
    
    # ---------- ۳. اجرای کوئری و فرمت کردن خروجی ----------
    result = await db.execute(query)
    
    products_with_sellers = [
        {
            'product_name': row.persian_name,
            'product_features': row.extra_features,
            'base_product_key': row.random_key,
            'sellers': row.sellers or []
        }
        for row in result.all()
    ]

    return products_with_sellers

async def find_products_with_aggregated_sellers_with_features(
    db: AsyncSession,
    filters_json: Dict[str, Any]
) -> List[Dict[str, Any]]:

    search_query_text = filters_json.get("search_query")
    structured_filters = filters_json.get("structured_filters", {})

    seller_filters = []
    if "price_min" in structured_filters and structured_filters["price_min"] is not None:
        seller_filters.append(models.Member.price >= structured_filters["price_min"])
    if "price_max" in structured_filters and structured_filters["price_max"] is not None:
        seller_filters.append(models.Member.price <= structured_filters["price_max"])
    if "has_warranty" in structured_filters and structured_filters["has_warranty"]:
        seller_filters.append(models.Shop.has_warranty == True)
    if "city_name" in structured_filters and structured_filters["city_name"]:
        seller_filters.append(models.City.name == structured_filters["city_name"])

    filtered_sellers_cte = (
        select(
            models.Member.base_random_key,
            func.jsonb_build_object(
                'member_key', models.Member.random_key, 'price', models.Member.price,
                'has_warranty', models.Shop.has_warranty, 'shop_score', models.Shop.score,
                'city', models.City.name, 'shop_id', models.Shop.id
            ).label("seller_data")
        )
        .join(models.Shop, models.Member.shop_id == models.Shop.id)
        .join(models.City, models.Shop.city_id == models.City.id)
        .where(and_(*seller_filters))
        .cte("filtered_sellers")
    )


    s_score_expr = literal_column("0.0").cast(Float)
    if search_query_text:
        s_score_expr = func.similarity(models.BaseProduct.persian_name, search_query_text)

    feature_filters = structured_filters.get("features", {})
    f_score_expr = literal_column("0.0").cast(Float)
    if feature_filters:
        f_score_clauses = [
            case(
                (models.BaseProduct.extra_features[key].as_string() == str(value), 1),
                else_=0
            ) for key, value in feature_filters.items()
        ]
        if f_score_clauses:
            raw_feature_score = sum(f_score_clauses)
            total_features_count = len(feature_filters)
            if total_features_count > 0:
                f_score_expr = cast(raw_feature_score, Float) / total_features_count
    
    total_score = (s_score_expr + (f_score_expr / 2.0)).label("total_score")

    query = (
        select(
            models.BaseProduct.persian_name,
            models.BaseProduct.random_key,
            models.BaseProduct.extra_features,
            func.jsonb_agg(filtered_sellers_cte.c.seller_data).label("sellers"),
            total_score
        )
        .join(filtered_sellers_cte, models.BaseProduct.random_key == filtered_sellers_cte.c.base_random_key)
        .group_by(models.BaseProduct.random_key, models.BaseProduct.persian_name, models.BaseProduct.extra_features)
    )
    
    if search_query_text or feature_filters:
        filter_conditions = []
        if search_query_text:
            filter_conditions.append(and_(
                models.BaseProduct.persian_name.op("%")(search_query_text),
                s_score_expr > 0.1
            ))
        
        if feature_filters:
            raw_feature_score_for_where = sum(
                 case((models.BaseProduct.extra_features[k].as_string() == str(v), 1), else_=0) 
                 for k, v in feature_filters.items()
            )
            filter_conditions.append(raw_feature_score_for_where > 0)

        if filter_conditions:
            query = query.where(or_(*filter_conditions))

        query = query.order_by(total_score.desc())
    else:
        query = query.order_by(func.count(filtered_sellers_cte.c.seller_data).desc())

    query = query.limit(10)
    
    result = await db.execute(query)
    
    products_with_sellers = [
        {
            'product_name': row.persian_name,
            'product_features': row.extra_features,
            'base_product_key': row.random_key,
            'sellers': row.sellers or []
        }
        for row in result.all()
    ]

    return products_with_sellers



async def find_similar_products(db: AsyncSession, product_name: str) -> List[Dict[str, str]]:
    """
    Asynchronously finds the top 10 most similar products by their Persian name.

    This function finds products with similar names to the search term,
    filters for a reasonable similarity threshold, and returns the top 10
    most relevant results.

    Args:
        db: The SQLAlchemy AsyncSession to use for the query.
        product_name: The search term to look for in the product names.

    Returns:
        A list of dictionaries, each containing the 'id' (random_key) and
        'product_name' (persian_name) of a matching product, or an empty
        list if no matches are found.
    """
    similarity_score = func.similarity(models.BaseProduct.persian_name, product_name)

    query = (
        select(
            models.BaseProduct.random_key,
            models.BaseProduct.persian_name
        )
        .where(
            models.BaseProduct.persian_name.op("%")(product_name),
            similarity_score > 0.1
        )
        .order_by(similarity_score.desc())
        .limit(10)
    )

    result = await db.execute(query)
    
    products_found = [
        {'id': row.random_key, 'product_name': row.persian_name}
        for row in result.all()
    ]
    
    return products_found

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

async def search_products_by_keywords_like(db: AsyncSession, keywords: List[str]) -> Optional[List[str]]:
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

async def get_product_rkey_by_name_like(db: AsyncSession, product_name: str) -> Optional[models.BaseProduct]:
    
    keywords = product_name.split()
    conditions = and_(*[models.BaseProduct.persian_name.ilike(f"%{keyword}%") for keyword in keywords])
    query = select(models.BaseProduct.random_key).where(conditions)
    result = await db.execute(query)
    
    keys = result.scalars().all()
    
    if keys:
        return keys
        
    return None
    return 


async def get_product_by_name_like(db: AsyncSession, product_name: str) -> Optional[models.BaseProduct]:
    
    # query = select(models.BaseProduct).where(
    #     models.BaseProduct.persian_name.contains(product_name)
    # )
    
    # NEW CODE
    keywords = product_name.split()
    conditions = and_(*[models.BaseProduct.persian_name.ilike(f"%{keyword}%") for keyword in keywords])
    query = select(models.BaseProduct).where(conditions)
    # END NEW CODE
    
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

def get_members_with_details_by_base_random_key(db, base_random_key: str):
    """
    برای یک base_random_key خاص، لیست تمام اعضا (ممبرها) را به همراه جزئیات کامل 
    فروشگاه و شهر به صورت JSON برمی‌گرداند.
    """
    results = (
        db.query(
            models.Member.price,
            models.Shop.id.label("shop_id"),
            models.Shop.has_warranty,
            models.Shop.score,
            models.City.name.label("city_name")
        )
        .join(models.Shop, models.Member.shop_id == models.Shop.id)
        .join(models.City, models.Shop.city_id == models.City.id)
        .filter(models.Member.base_random_key == base_random_key)
        .all()
    )

    members_list = []
    for row in results:
        members_list.append({
            "price": row.price,
            "shop_id": row.shop_id,
            "has_warranty": row.has_warranty,
            "shop_score": row.score,
            "city": row.city_name
        })
        
    return members_list