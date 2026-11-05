from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import MovementType

Quantity = Field(gt=0)
Reason = Field(default=None, max_length=255)


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReceiveRequest(_Request):
    product_id: int
    to_location_id: int
    quantity: int = Quantity
    reason: str | None = Reason


class PickRequest(_Request):
    product_id: int
    from_location_id: int
    quantity: int = Quantity
    reason: str | None = Reason


class MoveRequest(_Request):
    product_id: int
    from_location_id: int
    to_location_id: int
    quantity: int = Quantity
    reason: str | None = Reason

    @model_validator(mode="after")
    def locations_must_differ(self):
        if self.from_location_id == self.to_location_id:
            raise ValueError("from_location_id and to_location_id must be different")
        return self


class AdjustRequest(_Request):
    product_id: int
    location_id: int
    quantity_change: int
    reason: str = Field(min_length=1, max_length=255)

    @field_validator("quantity_change")
    @classmethod
    def change_must_not_be_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("quantity_change must not be 0")
        return value


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: MovementType
    product_id: int
    from_location_id: int | None
    to_location_id: int | None
    quantity: int
    reason: str | None
    user_id: int
    created_at: datetime


class InventoryLevel(BaseModel):
    location_id: int
    quantity: int


class MovementResponse(BaseModel):
    movement: MovementOut
    inventory: list[InventoryLevel]
