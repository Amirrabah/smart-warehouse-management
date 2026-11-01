# Project Structure — smart-warehouse-management

What every file does and how they connect.
Update this file at the end of each phase.

**Status:** Phases 0–2 and quality PR merged · Phase 3 complete (stock movements, 152 tests) · Row locking follows in Phase 4

## Folder overview

```
smart-warehouse-management/
├── .github/workflows/ci.yml
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   ├── README
│   └── versions/
│       ├── 6d7f438baf76_initial_empty_migration.py
│       ├── 5c21740ef948_create_users_table.py
│       ├── 61dc112b45e4_create_products_and_locations_tables.py
│       └── a25281f0285d_create_inventory_and_stock_movements_.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── security.py
│   ├── dependencies.py
│   ├── rate_limit.py
│   ├── seed.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── inventory.py
│   │   ├── location.py
│   │   ├── product.py
│   │   ├── stock_movement.py
│   │   └── user.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── location.py
│   │   ├── movement.py
│   │   ├── product.py
│   │   └── user.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── locations.py
│   │   ├── movements.py
│   │   ├── products.py
│   │   └── users.py
│   └── services/
│       ├── __init__.py
│       ├── movements.py
│       └── stock.py
├── docs/
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_health.py
│   ├── test_locations.py
│   ├── test_movement_service.py
│   ├── test_movements_api.py
│   ├── test_products.py
│   ├── test_security.py
│   ├── test_stock_models.py
│   ├── test_stock_service.py
│   └── test_users.py
├── .env.example
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── README.md
├── requirements.txt
└── ruff.toml
```

Not in Git (local only, on purpose): `.env` (real secrets), `.venv/` (installed packages).

## `app/` — the application

| File | Contains | Phase |
|---|---|---|
| `__init__.py` | Empty. Makes `app` a Python package. | 0 |
| `main.py` | Creates the FastAPI app, includes all routers, rate-limit handler (429), `StockConflict` → **409** and `NotFound` → **404** handlers, `GET /health` | 0–3 |
| `config.py` | `Settings`: reads `DATABASE_URL` and `JWT_SECRET` from environment / `.env`; normalises Railway's `postgresql://` to `postgresql+psycopg://` | 0 |
| `database.py` | `engine` (connection pool, `pool_pre_ping`), `SessionLocal`, `Base` (parent of all models), `get_db()` (one session per request, always closed) | 0 |
| `security.py` | `hash_password`, `verify_password` (bcrypt), `create_access_token`, `decode_access_token` (JWT, HS256, 60 min), `DUMMY_HASH` (timing protection) | 1 |
| `dependencies.py` | `get_current_user` (token → user from DB, else **401**), `require_roles(...)` (wrong role → **403**) | 1 |
| `rate_limit.py` | The shared slowapi `limiter` (login: 5 per minute per IP) | quality |
| `seed.py` | Creates the first admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME`. Idempotent. Run with `py -m app.seed`. | 1 |

### `app/models/` — database tables (SQLAlchemy)

| File | Contains |
|---|---|
| `__init__.py` | Exports `Location`, `Product`, `ProductUnit`, `User`, `UserRole` (Alembic imports this to see all tables) |
| `user.py` | `UserRole` enum (admin / worker / planner) and the `User` table: id, name, email (unique), password_hash, role (CHECK), is_active, created_at |
| `product.py` | `ProductUnit` enum (pcs / box / kg) and the `Product` table: id, sku (unique), name, unit (CHECK), reorder_point (CHECK ≥ 0), is_active, low_stock_alerted, created_at |
| `location.py` | `Location` table: id, code (unique, CHECK format `A-01-03`), description (optional), is_active |
| `inventory.py` | `Inventory` table — current stock: product_id, location_id, quantity, updated_at. UNIQUE (product, location), CHECK quantity >= 0 |
| `stock_movement.py` | `MovementType` enum (receive / pick / move / adjust) and `StockMovement` table — full history: type, product, from/to location, quantity (CHECK > 0), reason, user, created_at. `DIRECTION_RULE` CHECK enforces the from/to/reason rules per type. Index on (product_id, created_at) |

### `app/schemas/` — what the API accepts and returns (Pydantic)

| File | Contains |
|---|---|
| `__init__.py` | Empty |
| `auth.py` | `LoginRequest` (email, password ≤ 72), `TokenResponse` |
| `user.py` | `UserOut` (no password), `UserCreate` (email normalised), `UserUpdate` (partial, `extra="forbid"`) |
| `product.py` | `ProductOut`, `ProductCreate` (SKU normalised to upper case), `ProductUpdate` (name, is_active only — SKU and unit locked), `ReorderPointUpdate` |
| `location.py` | `LocationOut`, `LocationCreate` (code normalised, must match `A-01-03`), `LocationUpdate` (description, is_active — code locked) |
| `movement.py` | `ReceiveRequest`, `PickRequest`, `MoveRequest` (from ≠ to), `AdjustRequest` (change ≠ 0, reason required), `MovementOut`, `MovementResponse` (`{movement, inventory}`) |

Rule: **models** describe the database, **schemas** describe the API. `password_hash` exists only in the model.

### `app/routers/` — endpoints

| File | Endpoints | Allowed roles |
|---|---|---|
| `__init__.py` | Empty | |
| `auth.py` | `POST /auth/login` | public |
| | `GET /auth/me` | any logged-in user |
| `users.py` | `GET /users`, `POST /users`, `PATCH /users/{id}` | admin |
| `products.py` | `GET /products?search=&active=`, `GET /products/{id}` | any logged-in user |
| | `POST /products`, `PATCH /products/{id}` | admin |
| | `PATCH /products/{id}/reorder-point` | admin, planner |
| `locations.py` | `GET /locations?active=`, `GET /locations/{id}` | any logged-in user |
| | `POST /locations`, `PATCH /locations/{id}` (deactivating a location that holds stock → **409**) | admin |
| `movements.py` | `POST /movements/receive`, `/pick`, `/move`, `/adjust` — each returns **201** with the movement and new stock per location | admin, worker |

### `app/services/` — business logic (no HTTP)

| File | Contains |
|---|---|
| `__init__.py` | Empty |
| `stock.py` | `increase_stock` (upsert: `INSERT … ON CONFLICT DO UPDATE`), `decrease_stock` (rejects missing / insufficient stock), `StockConflict` (→ 409). Never commits. |
| `movements.py` | `receive`, `pick`, `move`, `adjust`: check product/location exist and are active (`NotFound` → 404, `StockConflict` → 409), change stock, record the movement, **one commit**. `_all_or_nothing` rolls back on any error. |

Rule: routers handle HTTP (schemas, roles, status codes); services handle the warehouse rules. Services can be tested without HTTP.

## `alembic/` + `alembic.ini` — migrations

| File | Contains |
|---|---|
| `alembic.ini` | Alembic settings. **No database URL** (it comes from `settings`). `prepend_sys_path = .` |
| `env.py` | Uses `settings.database_url` and `Base.metadata`; `import app.models` registers all tables |
| `script.py.mako` | Template for new migration files |
| `README` | Generated by Alembic, not important |
| `versions/6d7f438baf76_…` | Migration 1: empty, proves the setup |
| `versions/5c21740ef948_…` | Migration 2: `users` table, unique index on email, CHECK on role |
| `versions/61dc112b45e4_…` | Migration 3: `products` and `locations` tables, unique SKU and code, CHECKs on unit, reorder point and code format |
| `versions/a25281f0285d_…` | Migration 4: `inventory` and `stock_movements` tables, all foreign keys, unique (product, location), CHECKs on quantity and movement direction, index on (product_id, created_at) |

Commands:

```powershell
py -m alembic revision --autogenerate -m "message"   # create (then READ the file)
py -m alembic upgrade head                           # apply
py -m alembic downgrade -1                           # undo one step
py -m alembic current                                # show version
```

The container runs `alembic upgrade head` automatically on start.

## `tests/`

| File | Proves |
|---|---|
| `conftest.py` | Not tests — shared fixtures: `test_engine` (creates `warehouse_test`), `db` (empties tables after each test), `client` (app uses the test DB), `make_user`, `auth_header` |
| `test_health.py` | `/health` returns 200 `{"status": "ok"}` |
| `test_security.py` | hash ≠ password, verify works, salting, token round trip, tampered token rejected |
| `test_auth.py` | login (valid, case-insensitive email, wrong password, unknown email, inactive), `/auth/me`, deactivated user blocked, seed is idempotent |
| `test_users.py` | worker and planner get 403 on all `/users` endpoints, no token gets 401, admin can list / create / update, duplicates 409, bad input 422, admin cannot demote or deactivate self |
| `test_products.py` | only admin creates/edits, admin + planner change reorder point, all roles can view, SKU normalised, duplicate SKU 409, bad input 422, SKU/unit locked, search by SKU or name, active filter |
| `test_locations.py` | only admin creates/edits, all roles can view, code normalised, invalid codes 422, duplicate code 409, code locked, sorted list, active filter |
| `test_stock_models.py` | database rules: no negative stock, one row per product+location, valid and invalid movement directions, quantity > 0 |
| `test_stock_service.py` | increase creates/adds, decrease reduces, exact zero keeps the row, insufficient or missing stock rejected and unchanged |
| `test_movement_service.py` | receive / pick / move / adjust change stock and record a movement with user; failures change nothing; inactive → conflict; unknown → not found; database rejection rolls back |
| `test_movements_api.py` | planner 403 and no token 401 on all four; admin + worker 201; full flow; 409 / 404 / 422 cases; location with stock cannot be deactivated |

Run with `py -m pytest -v` (needs the database: `docker compose up -d db`). 152 tests.

Phase 3 was built test-first (red → green): each test was seen failing before the code existed.

## `docs/` — design documents

| File | Contains |
|---|---|
| `project-brief.md` | Problem, users, MVP, out of scope, phases, success criteria |
| `data-model.md` | All tables, constraints, movement rules, notifications |
| `api-endpoints.md` | All planned endpoints with roles and status codes |
| `transaction-flows.md` | Transaction steps for receive / pick / move / adjust (implemented in Phase 3; row locking in Phase 4) |
| `project-structure.md` | This file |

## Root — infrastructure and config

| File | Contains |
|---|---|
| `Dockerfile` | Python 3.14-slim → install requirements → copy `alembic/` and `app/` → `alembic upgrade head && uvicorn` on `${PORT:-8000}` |
| `docker-compose.yml` | `db` (Postgres 17, healthcheck, `pgdata` volume, host port **5433** because a Windows PostgreSQL uses 5432) + `api` (waits for healthy db, `DATABASE_URL` uses host `db`) |
| `.github/workflows/ci.yml` | On every push and PR: Postgres service → install → Ruff lint + format check → migrate → pytest |
| `ruff.toml` | Ruff rules (E, F, I, B, UP, S), line length 100, `app` first-party, migrations excluded |
| `requirements.txt` | Pinned packages. Update with `py -m pip freeze \| Set-Content -Encoding ascii requirements.txt` |
| `.env.example` | Variable names with placeholder values (committed) |
| `.gitignore` | Keeps `.env`, `.venv`, `__pycache__` out of Git |
| `README.md` | Title only — written in Phase 9 |

## How a request flows through the files

Example: a worker calls `GET /users`.

```
Request: GET /users + Authorization: Bearer eyJ...
   │
   ▼
main.py ─────────► routers/users.py → list_users()
                         │ needs AdminUser
                         ▼
                   dependencies.py → require_roles(ADMIN)
                         │ needs the current user
                         ▼
                   dependencies.py → get_current_user()
                         │ ├─ security.py → decode_access_token()   (bad token → 401)
                         │ └─ database.py → get_db() → models/user.py (user from DB)
                         ▼
                   role == admin?   no → 403    yes → continue
                         ▼
                   query users → schemas/user.py → UserOut (no password_hash)
                         ▼
Response: 200 [...]   or   403 {"detail": "Not enough permissions"}
```

Debugging map:

| Symptom | Look in |
|---|---|
| 401 | `security.py`, `get_current_user` in `dependencies.py` |
| 403 | `require_roles` in `dependencies.py`, the route's role list |
| 422 | the schema in `app/schemas/` |
| 409 | database constraint (unique / check) or explicit check in the router |
| 500 | uvicorn terminal output, read the traceback from the bottom |
| Wrong field in response | the `response_model` schema |
