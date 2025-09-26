from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class Scenario4State(BaseModel):
    """
    این کلاس وضعیت یک مکالمه در سناریو 4 را نمایندگی می‌کند.
    """
    state: int = 1
    chat_history: List[Dict[str, Any]] = []
    filters_json: Optional[Dict[str, Any]] = None
    products_with_sellers: Optional[List[Dict[str, Any]]] = None
    product_features: str = None
    selected_product: Optional[Dict[str, Any]] = None