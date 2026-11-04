from pydantic import BaseModel

from app.models import ProductUnit


class StockSummary(BaseModel):
    product_id: int
    sku: str
    name: str
    unit: ProductUnit
    reorder_point: int
    total: int
    below_reorder: bool
