# Transaction Flows — smart-warehouse-management

How each stock operation runs inside the database: what gets checked, what gets locked, in what order.
Related: [data-model.md](data-model.md), [api-endpoints.md](api-endpoints.md).

## 1. Why this document exists

Two workers can press "Pick" at the same moment. Without a plan, both read `quantity = 1`, both subtract 1, and either the stock goes to −1 or one pick silently vanishes (a **lost update**). Every flow below follows the same pattern to make that impossible.

## 2. The common pattern

Every movement endpoint runs this sequence in **one transaction**:

```
BEGIN
  1. Validate input                        → 422   (Pydantic, before BEGIN really)
  2. Load product + location(s)            → 404 if missing, 409 if inactive
  3. Lock the inventory row(s) FOR UPDATE  → always in ascending location_id order
  4. Check stock                           → 409 if no row / not enough
  5. UPDATE / UPSERT inventory
  6. INSERT stock_movements row
COMMIT                                     → any error → ROLLBACK, nothing is saved
```

Key ideas:

| Idea | What it does |
|---|---|
| **One transaction** | Inventory and movement are saved together or not at all. You never get stock without history, or history without stock. |
| **`SELECT ... FOR UPDATE`** | Locks the inventory row. A second transaction that wants the same row **waits** until the first commits, then reads the *new* quantity. |
| **Fixed lock order** | When two rows are locked (move), always lock the lower `location_id` first. This prevents deadlocks (see §7). |
| **`CHECK (quantity >= 0)`** | Last safety net. If a code bug skips the check, the database refuses the update. The API catches `IntegrityError` → `409`. |
| **Default isolation (READ COMMITTED)** | Enough, because the row lock forces a fresh read after waiting. No need for SERIALIZABLE. |

## 3. Receive

`POST /movements/receive` — `product_id`, `to_location_id`, `quantity`

```
BEGIN
  product  = SELECT * FROM products  WHERE id = :product_id        → 404 / 409 if inactive
  location = SELECT * FROM locations WHERE id = :to_location_id    → 404 / 409 if inactive

  INSERT INTO inventory (product_id, location_id, quantity)
  VALUES (:product_id, :to_location_id, :quantity)
  ON CONFLICT (product_id, location_id)
  DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
  RETURNING quantity

  INSERT INTO stock_movements (type, product_id, from_location_id, to_location_id,
                               quantity, user_id, reason)
  VALUES ('receive', :product_id, NULL, :to_location_id, :quantity, :user_id, :reason)
COMMIT
```

Why no explicit `FOR UPDATE`: the upsert locks the row itself. If the row doesn't exist yet and two receives arrive together, `UNIQUE (product_id, location_id)` makes one insert and the other turns into an update. Both quantities are counted.

## 4. Pick

`POST /movements/pick` — `product_id`, `from_location_id`, `quantity`

```
BEGIN
  check product + location exist and are active                   → 404 / 409

  row = SELECT * FROM inventory
        WHERE product_id = :product_id AND location_id = :from_location_id
        FOR UPDATE
  if row is None:                 → 409 "No stock of this product at this location"
  if row.quantity < :quantity:    → 409 "Insufficient stock: X available, Y requested"

  UPDATE inventory SET quantity = quantity - :quantity WHERE id = row.id

  INSERT stock_movements ('pick', from = :from_location_id, to = NULL, ...)
COMMIT
```

### The concurrency case (Phase 4 test)

Stock is 1, and worker A and worker B both pick 1:

| Time | Worker A | Worker B |
|---|---|---|
| t1 | `BEGIN`; `SELECT ... FOR UPDATE` → gets lock, quantity = 1 | |
| t2 | | `BEGIN`; `SELECT ... FOR UPDATE` → **waits** |
| t3 | 1 ≥ 1 ✔; `UPDATE` → 0; insert movement; `COMMIT` | |
| t4 | | lock granted, reads **fresh** quantity = 0 |
| t5 | | 0 < 1 → `409`, `ROLLBACK` |

Result: exactly one success, stock = 0, one movement. That is the success criterion from the brief.

## 5. Move

`POST /movements/move` — `product_id`, `from_location_id`, `to_location_id`, `quantity`
(`from = to` is already rejected with `422` by the schema.)

```
BEGIN
  check product + both locations exist and are active             → 404 / 409

  -- lock both rows in ONE query, in fixed order
  rows = SELECT * FROM inventory
         WHERE product_id = :product_id
           AND location_id IN (:from_location_id, :to_location_id)
         ORDER BY location_id
         FOR UPDATE

  from_row = row where location_id = :from_location_id
  if from_row is None:                 → 409
  if from_row.quantity < :quantity:    → 409

  UPDATE inventory SET quantity = quantity - :quantity WHERE id = from_row.id

  -- to-row may not exist yet → upsert (same as receive)
  INSERT INTO inventory (...) VALUES (:product_id, :to_location_id, :quantity)
  ON CONFLICT (product_id, location_id)
  DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity

  INSERT stock_movements ('move', from = :from_location_id, to = :to_location_id, ...)
COMMIT
```

Why the `ORDER BY location_id`: Postgres locks rows in the order it returns them. With this ordering, a move A→B and a move B→A both lock A first, so one simply waits for the other instead of deadlocking.

## 6. Adjust

`POST /movements/adjust` — `product_id`, `location_id`, `quantity_change` (≠ 0), `reason` (required)

```
if quantity_change < 0:
    run the PICK flow with quantity = abs(quantity_change), from = location_id
    movement: type 'adjust', from = location_id, to = NULL, reason = :reason
else:
    run the RECEIVE flow with quantity = quantity_change, to = location_id
    movement: type 'adjust', from = NULL, to = location_id, reason = :reason
```

Same locking and same `409` rules. Adjust only adds the required reason and the sign translation.

Code tip: write two internal helpers, `_decrease_stock(db, product_id, location_id, qty)` and `_increase_stock(db, product_id, location_id, qty)`. Then:
- pick = decrease
- receive = increase
- move = decrease + increase
- adjust = one of the two

The locking logic lives in one place.

## 7. Deactivating a location

`PATCH /locations/{id}` with `is_active = false`

```
BEGIN
  location = SELECT * FROM locations WHERE id = :id FOR UPDATE
  total    = SELECT COALESCE(SUM(quantity), 0) FROM inventory WHERE location_id = :id
  if total > 0:  → 409 "Location still holds stock"
  UPDATE locations SET is_active = false WHERE id = :id
COMMIT
```

Edge case: a receive into this location could start at the same moment. To make that impossible, the movement flows can read the location with `SELECT ... FOR SHARE`. Share locks don't block each other, but they do block the `FOR UPDATE` above. This is optional for v1, but the fix is a one-word change, so note it.

Inventory rows that reach `0` are **kept**, not deleted. That's simpler (no deletes on inventory), and the overview just filters `quantity > 0`.

## 8. Nightly low-stock job

`run_low_stock_check(db)`, run by the scheduler once a night (time in UTC, documented in README).

```
BEGIN
  totals = SELECT p.id, p.sku, p.name, p.reorder_point, p.low_stock_alerted,
                  COALESCE(SUM(i.quantity), 0) AS total
           FROM products p LEFT JOIN inventory i ON i.product_id = p.id
           WHERE p.is_active
           GROUP BY p.id

  new_low  = [t for t in totals if t.total < t.reorder_point and not t.low_stock_alerted]
  restored = [t for t in totals if t.total >= t.reorder_point and t.low_stock_alerted]

  UPDATE products SET low_stock_alerted = false WHERE id IN (restored ids)

  if new_low:
      recipients = SELECT id FROM users
                   WHERE is_active AND role IN ('admin', 'planner')
      for user in recipients:
          INSERT INTO notifications (user_id, title, body, created_at, read_at)
          VALUES (user.id, 'Low stock: N products', <list of SKU + total>, now(), NULL)
      UPDATE products SET low_stock_alerted = true WHERE id IN (new_low ids)
COMMIT
```

Why it's one transaction: if inserting notifications fails, the flags are not set either. The next night retries cleanly instead of marking products as "alerted" without anyone being told.

Why a reset step: without it, a product that was low once, got restocked, and then dropped low again would never alert a second time.

## 9. Error mapping (one place in the code)

| Source | HTTP |
|---|---|
| Your own check (no row / not enough / inactive) | `409` |
| `IntegrityError` from `CHECK (quantity >= 0)` | `409` |
| `IntegrityError` from a `UNIQUE` (SKU, code, email) | `409` |
| `DeadlockDetected` (shouldn't happen with fixed order) | `503`, logged, client may retry |

## 10. SQLAlchemy shape (for Phase 3)

```python
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

def _decrease_stock(db, product_id: int, location_id: int, qty: int) -> int:
    row = db.execute(
        select(Inventory)
        .where(Inventory.product_id == product_id,
               Inventory.location_id == location_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise StockConflict("No stock of this product at this location")
    if row.quantity < qty:
        raise StockConflict(f"Insufficient stock: {row.quantity} available, {qty} requested")
    row.quantity -= qty
    return row.quantity

def _increase_stock(db, product_id: int, location_id: int, qty: int) -> int:
    stmt = (
        insert(Inventory)
        .values(product_id=product_id, location_id=location_id, quantity=qty)
        .on_conflict_do_update(
            index_elements=["product_id", "location_id"],
            set_={"quantity": Inventory.quantity + qty},
        )
        .returning(Inventory.quantity)
    )
    return db.execute(stmt).scalar_one()
```

The route wraps the helpers and the movement insert in `with db.begin():` (or commits once at the end), so everything succeeds or fails together. `StockConflict` is a custom exception that a single exception handler turns into `409`.

## 11. Tests this document implies

| Test | Expect |
|---|---|
| Two threads pick the last item at the same time (real Postgres, separate sessions) | exactly one `201`, one `409`, quantity 0, one movement |
| Two simultaneous first receives into an empty location | quantity = sum of both, two movements |
| Move A→B and B→A at the same time | both succeed, no deadlock, totals unchanged |
| Pick from location with no inventory row | `409` |
| Pick more than available | `409`, inventory unchanged, no movement |
| Movement on inactive product / location | `409` |
| Negative adjust below zero | `409` |
| Deactivate location with stock | `409` |
| Nightly job twice in a row | notifications created once |
| Low → restocked → low again | alerts twice |
