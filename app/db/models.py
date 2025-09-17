from sqlalchemy import (
    Column,
    String,
    BigInteger,
    Float,
    Boolean,
    DateTime,
    ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()



class Search(Base):
    """
    Model for the 'searches' table.
    Logs each page of search results shown to a user.
    """
    __tablename__ = "searches"

    id = Column(String, primary_key=True)
    uid = Column(String, index=True)
    page = Column(BigInteger)
    session_id = Column(String)
    timestamp = Column(DateTime(timezone=True))
    query = Column(String, index=True)
    result_base_product_rks = Column(JSONB)
    category_id = Column(BigInteger)
    category_brand_boosts = Column(JSONB)

class BaseView(Base):
    """
    Model for the 'base_views' table.
    Logs user views of a base product page.
    """
    __tablename__ = "base_views"

    id = Column(String, primary_key=True)
    search_id = Column(String, ForeignKey("searches.id"), index=True)
    base_product_rk = Column(String, ForeignKey("base_products.random_key"), index=True)
    timestamp = Column(DateTime(timezone=True))

class FinalClick(Base):
    """
    Model for the 'final_clicks' table.
    Logs clicks that lead from a product page to a specific shop.
    """
    __tablename__ = "final_clicks"
    
    id = Column(String, primary_key=True)
    shop_id = Column(BigInteger, ForeignKey("shops.id"), index=True)
    base_view_id = Column(String, ForeignKey("base_views.id"), index=True)
    timestamp = Column(DateTime(timezone=True))



class BaseProduct(Base):
    """
    Model for the 'base_products' table.
    Represents a core product, independent of any specific seller.
    """
    __tablename__ = "base_products"

    image_url = Column(String)
    random_key = Column(String, primary_key=True, index=True)
    category_id = Column(BigInteger, ForeignKey("categories.id"))
    brand_id = Column(BigInteger, ForeignKey("brands.id"))
    english_name = Column(String)
    persian_name = Column(String, index=True)
    extra_features = Column(JSONB)
    members = Column(JSONB)

class Member(Base):
    """
    Model for the 'members' table.
    Represents a product as offered by a specific shop (a listing).
    """
    __tablename__ = "members"

    random_key = Column(String, primary_key=True, index=True)
    shop_id = Column(BigInteger, ForeignKey("shops.id"), index=True)
    price = Column(BigInteger)
    base_random_key = Column(String, ForeignKey("base_products.random_key"), index=True)

class Shop(Base):
    """
    Model for the 'shops' table.
    Represents a seller or vendor.
    """
    __tablename__ = "shops"

    id = Column(BigInteger, primary_key=True)
    city_id = Column(BigInteger, ForeignKey("cities.id"))
    score = Column(Float)
    has_warranty = Column(Boolean)
    city = relationship("City") 



class Category(Base):
    """
    Model for the 'categories' table.
    """
    __tablename__ = "categories"

    id = Column(BigInteger, primary_key=True)
    title = Column(String)
    parent_id = Column(BigInteger)

class Brand(Base):
    """
    Model for the 'brands' table.
    """
    __tablename__ = "brands"

    id = Column(BigInteger, primary_key=True)
    title = Column(String)

class City(Base):
    """
    Model for the 'cities' table.
    """
    __tablename__ = "cities"

    id = Column(BigInteger, primary_key=True)
    name = Column(String)