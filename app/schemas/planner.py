from pydantic import BaseModel

from app.models import ProductUnit


class PlannerRow(BaseModel):
    product_id: int
    sku: str
    name: str
    unit: ProductUnit
    reorder_point: int
    total: int
    below_reorder: bool
    used_last_30_days: int
    avg_daily_usage: float
    days_left: float | None
