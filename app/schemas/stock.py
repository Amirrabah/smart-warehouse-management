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


class LocationQuantity(BaseModel):
    location_id: int
    code: str
    quantity: int


class ProductStock(StockSummary):
    """One product: the summary plus where the stock is (locations with quantity > 0)."""

    locations: list[LocationQuantity]


class ShelfItem(BaseModel):
    product_id: int
    sku: str
    name: str
    unit: ProductUnit
    quantity: int
