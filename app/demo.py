"""Demo data for the public demo (DEMO_MODE=true).

reset_demo() wipes EVERY table and fills the warehouse with a month of realistic history:
products, shelves, receives, picks, moves and count adjustments, one login per role and a
low-stock notification. All stock changes go through the real movement services, so stock
and history always agree; afterwards the movement times are spread over the last 30 days.

Run by hand:  py -m app.demo   (refuses unless DEMO_MODE=true)
"""

import logging
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal
from app.models import Location, Product, ProductUnit, StockMovement, User, UserRole
from app.security import hash_password
from app.services import movements
from app.services.alerts import run_low_stock_check

logger = logging.getLogger(__name__)

# Public on purpose: it is shown on the login page of the demo.
DEMO_PASSWORD = "demo-warehouse"  # noqa: S105


@dataclass(frozen=True)
class DemoUser:
    name: str
    email: str
    role: UserRole


DEMO_USERS = (
    DemoUser("Alex Admin", "admin@example.com", UserRole.ADMIN),
    DemoUser("Wren Worker", "worker@example.com", UserRole.WORKER),
    DemoUser("Parker Planner", "planner@example.com", UserRole.PLANNER),
)

LOCATIONS = (
    ("A-01-01", "Small parts, eye level"),
    ("A-01-02", "Small parts"),
    ("A-01-03", "Cables"),
    ("A-01-04", "Cables, overflow"),
    ("A-02-01", "Packaging"),
    ("B-01-01", "Bulk, floor level"),
    ("B-01-02", "Bulk"),
    ("B-02-01", "Pallet rack"),
    ("C-01-01", "Returns"),
    ("D-01-01", "Overflow"),
)


@dataclass(frozen=True)
class DemoProduct:
    sku: str
    name: str
    unit: ProductUnit
    reorder_point: int
    start: int  # received 32 days ago
    per_day: float  # average picked per day
    shelf: str  # where it is received and picked
    restock: tuple[int, int] | None = None  # (days ago, quantity)


PRODUCTS = (
    DemoProduct("CAB-USBC-1M", "USB-C cable 1 m", ProductUnit.PCS, 100, 300, 8, "A-01-03"),
    DemoProduct("CAB-HDMI-2M", "HDMI cable 2 m", ProductUnit.PCS, 40, 150, 3, "A-01-03"),
    DemoProduct(
        "BOX-S", "Shipping box, small", ProductUnit.BOX, 60, 400, 10, "A-02-01", restock=(15, 200)
    ),
    DemoProduct("BOX-M", "Shipping box, medium", ProductUnit.BOX, 40, 200, 6, "A-02-01"),
    DemoProduct("TAPE-48", "Packing tape 48 mm", ProductUnit.PCS, 50, 240, 5, "A-01-02"),
    DemoProduct("LBL-A6", "Shipping labels A6", ProductUnit.BOX, 10, 40, 1.2, "A-01-01"),
    DemoProduct("GLV-NIT-M", "Nitrile gloves, size M", ProductUnit.BOX, 15, 60, 0.8, "A-01-01"),
    DemoProduct("WRAP-500", "Pallet stretch wrap", ProductUnit.PCS, 12, 50, 1.5, "B-01-01"),
    DemoProduct("SALT-25", "De-icing salt", ProductUnit.KG, 200, 1500, 25, "B-02-01"),
    DemoProduct("SCAN-BAT", "Scanner battery", ProductUnit.PCS, 6, 30, 0, "A-01-01"),
    DemoProduct("BIT-SET", "Drill bit set", ProductUnit.PCS, 5, 18, 0.3, "A-01-02"),
    DemoProduct("MARK-BLK", "Permanent marker, black", ProductUnit.PCS, 24, 0, 0, "A-01-02"),
)


def _wipe(db: Session) -> None:
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db.commit()


def _at(now: datetime, days_ago: int, hour: int, minute: int = 0) -> datetime:
    day = (now - timedelta(days=days_ago)).replace(hour=hour, minute=minute, second=0)
    return min(day, now - timedelta(minutes=1))  # never in the future


def reset_demo(db: Session, now: datetime | None = None) -> None:
    """Delete everything and load the demo warehouse. Deterministic (same data every night)."""
    now = now or datetime.now(UTC)
    rng = random.Random(7)  # noqa: S311  (demo data, not security)
    _wipe(db)

    created = now - timedelta(days=35)
    users = {}
    for account in DEMO_USERS:
        user = User(
            name=account.name,
            email=account.email,
            password_hash=hash_password(DEMO_PASSWORD),
            role=account.role,
            created_at=created,
        )
        db.add(user)
        users[account.role] = user
    shelves = {code: Location(code=code, description=desc) for code, desc in LOCATIONS}
    products = {
        p.sku: Product(
            sku=p.sku, name=p.name, unit=p.unit, reorder_point=p.reorder_point, created_at=created
        )
        for p in PRODUCTS
    }
    db.add_all([*shelves.values(), *products.values()])
    db.commit()

    admin, worker = users[UserRole.ADMIN], users[UserRole.WORKER]
    times: list[dict] = []  # movement id -> when it "happened"

    def record(result: movements.MovementResult, when: datetime) -> None:
        times.append({"id": result.movement.id, "created_at": when})

    stock = {p.sku: p.start for p in PRODUCTS}  # at the product's own shelf

    # 32 days ago: the opening delivery.
    for p in PRODUCTS:
        if p.start:
            pid, loc = products[p.sku].id, shelves[p.shelf].id
            record(
                movements.receive(db, worker, pid, loc, p.start, "Opening delivery"),
                _at(now, 32, 9, rng.randint(0, 59)),
            )

    # The last 30 days: daily picks, one restock, a move to overflow and two count corrections.
    for days_ago in range(30, 0, -1):
        for p in PRODUCTS:
            pid, loc = products[p.sku].id, shelves[p.shelf].id
            if p.restock and p.restock[0] == days_ago:
                record(
                    movements.receive(db, worker, pid, loc, p.restock[1], "Supplier delivery"),
                    _at(now, days_ago, 8, 15),
                )
                stock[p.sku] += p.restock[1]
            if p.per_day >= 1:
                quantity = rng.randint(0, round(2 * p.per_day))
            else:
                quantity = 1 if rng.random() < p.per_day else 0
            quantity = min(quantity, stock[p.sku])
            if quantity:
                record(
                    movements.pick(db, worker, pid, loc, quantity, None),
                    _at(now, days_ago, rng.randint(8, 16), rng.randint(0, 59)),
                )
                stock[p.sku] -= quantity

        if days_ago == 20:
            cables, overflow = products["CAB-USBC-1M"].id, shelves["A-01-04"].id
            record(
                movements.move(
                    db, admin, cables, shelves["A-01-03"].id, overflow, 40, "Make room on A-01-03"
                ),
                _at(now, days_ago, 17, 30),
            )
        if days_ago == 12:
            record(
                movements.adjust(
                    db, worker, products["BOX-M"].id, shelves["A-02-01"].id, -3, "3 boxes crushed"
                ),
                _at(now, days_ago, 16, 45),
            )
            stock["BOX-M"] -= 3
        if days_ago == 5:
            record(
                movements.adjust(
                    db, worker, products["TAPE-48"].id, shelves["A-01-02"].id, 2, "Found in count"
                ),
                _at(now, days_ago, 16, 50),
            )
            stock["TAPE-48"] += 2

    db.execute(update(StockMovement), times)
    db.commit()
    run_low_stock_check(db)


def ensure_demo_data(db: Session) -> bool:
    """Load the demo only into an empty database (first start). Returns True if it did."""
    if db.scalar(select(func.count()).select_from(User)):
        return False
    reset_demo(db)
    return True


def seed_demo_if_empty() -> None:
    """Called when the app starts in demo mode."""
    with SessionLocal() as db:
        if ensure_demo_data(db):
            logger.info("Demo data loaded into the empty database")


def main() -> None:
    if not settings.demo_mode:
        sys.exit("Refusing: this deletes ALL data. Set DEMO_MODE=true to reset a demo database.")
    with SessionLocal() as db:
        reset_demo(db)
    print("Demo data reset.")


if __name__ == "__main__":
    main()
