import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MovementType(enum.StrEnum):
    RECEIVE = "receive"
    PICK = "pick"
    MOVE = "move"
    ADJUST = "adjust"


DIRECTION_RULE = """
    (type = 'receive' AND from_location_id IS NULL AND to_location_id IS NOT NULL)
    OR (type = 'pick' AND from_location_id IS NOT NULL AND to_location_id IS NULL)
    OR (type = 'move' AND from_location_id IS NOT NULL AND to_location_id IS NOT NULL
        AND from_location_id <> to_location_id)
    OR (type = 'adjust' AND (from_location_id IS NULL) <> (to_location_id IS NULL)
        AND reason IS NOT NULL AND length(trim(reason)) > 0)
"""


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_movements_quantity_positive"),
        CheckConstraint(DIRECTION_RULE, name="ck_stock_movements_direction"),
        Index("ix_stock_movements_product_created", "product_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[MovementType] = mapped_column(
        Enum(
            MovementType,
            native_enum=False,
            create_constraint=True,
            length=10,
            values_callable=lambda types: [t.value for t in types],
        )
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    quantity: Mapped[int]
    reason: Mapped[str | None] = mapped_column(String(255))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
