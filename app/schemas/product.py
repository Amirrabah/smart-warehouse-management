from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ProductUnit

SKU_PATTERN = r"^[A-Z0-9][A-Z0-9-]*$"


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    unit: ProductUnit
    reorder_point: int
    is_active: bool
    created_at: datetime


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: str = Field(min_length=1, max_length=50, pattern=SKU_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    unit: ProductUnit
    reorder_point: int = Field(default=0, ge=0)

    @field_validator("sku", mode="before")
    @classmethod
    def normalise_sku(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class ReorderPointUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reorder_point: int = Field(ge=0)
