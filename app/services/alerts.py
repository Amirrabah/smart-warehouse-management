from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Inventory, Notification, Product, User, UserRole


@dataclass
class LowStockResult:
    alerted: list[str] = field(default_factory=list)  # SKUs that got a new alert
    restored: list[str] = field(default_factory=list)  # SKUs back at or above reorder point
    notifications: int = 0


def _message(low: list) -> tuple[str, str]:
    count = len(low)
    title = f"Low stock: {count} product{'' if count == 1 else 's'}"
    body = "\n".join(
        f"{row.sku} {row.name}: {row.total} left (reorder point {row.reorder_point})" for row in low
    )
    return title, body


def run_low_stock_check(db: Session) -> LowStockResult:
    """The nightly job: alert admins and planners about products that ran low.

    - A product is alerted once per shortage (products.low_stock_alerted).
    - When stock is back at or above the reorder point, the flag is cleared,
      so the product can alert again the next time it runs low.
    - Everything happens in one transaction: either all of it is saved, or nothing.
    """
    try:
        total = func.coalesce(func.sum(Inventory.quantity), 0)
        rows = db.execute(
            select(
                Product.id,
                Product.sku,
                Product.name,
                Product.reorder_point,
                Product.low_stock_alerted,
                total.label("total"),
            )
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .where(Product.is_active)
            .group_by(Product.id)
            .order_by(Product.sku)
        ).all()

        new_low = [r for r in rows if r.total < r.reorder_point and not r.low_stock_alerted]
        restored = [r for r in rows if r.total >= r.reorder_point and r.low_stock_alerted]
        result = LowStockResult(restored=[r.sku for r in restored])

        for row in restored:
            db.get(Product, row.id).low_stock_alerted = False

        recipients = db.scalars(
            select(User.id).where(User.is_active, User.role.in_([UserRole.ADMIN, UserRole.PLANNER]))
        ).all()

        if new_low and recipients:
            for row in new_low:
                db.get(Product, row.id).low_stock_alerted = True
            db.flush()
            title, body = _message(new_low)
            db.add_all(
                Notification(user_id=user_id, title=title, body=body) for user_id in recipients
            )
            result.alerted = [r.sku for r in new_low]
            result.notifications = len(recipients)

        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
