# Project Structure — smart-warehouse-management

What every file does and how they connect.
Update this file at the end of each phase.

**Status:** Phases 0–7 merged · Phase 8 complete (frontend in `app/static/`, served at `/app`, 316 tests incl. browser smoke tests)

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
│       ├── a25281f0285d_create_inventory_and_stock_movements_.py
│       └── 1dfb42dda5bc_create_notifications_table.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── security.py
│   ├── dependencies.py
│   ├── pagination.py
│   ├── rate_limit.py
│   ├── scheduler.py
│   ├── seed.py
│   ├── static/            (the frontend, see below)
│   │   ├── *.html         (11 pages)
│   │   ├── css/style.css
│   │   └── js/            (one module per page + api.js, dom.js, layout.js, lookups.js)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── inventory.py
│   │   ├── location.py
│   │   ├── notification.py
│   │   ├── product.py
│   │   ├── stock_movement.py
│   │   └── user.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── location.py
│   │   ├── movement.py
│   │   ├── notification.py
│   │   ├── planner.py
│   │   ├── product.py
│   │   ├── stock.py
│   │   └── user.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── locations.py
│   │   ├── movements.py
│   │   ├── notifications.py
│   │   ├── planner.py
│   │   ├── products.py
│   │   ├── stock.py
│   │   └── users.py
│   └── services/
│       ├── __init__.py
│       ├── alerts.py
│       ├── history.py
│       ├── movements.py
│       ├── notifications.py
│       ├── overview.py
│       ├── planner.py
│       └── stock.py
├── docs/
├── tests/
│   ├── e2e/test_smoke.py
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_concurrency.py
│   ├── test_frontend.py
│   ├── test_health.py
│   ├── test_locations.py
│   ├── test_low_stock_job.py
│   ├── test_movement_history_api.py
│   ├── test_movement_service.py
│   ├── test_movements_api.py
│   ├── test_notification_model.py
│   ├── test_notifications_api.py
│   ├── test_planner_api.py
│   ├── test_products.py
│   ├── test_scheduler.py
│   ├── test_security.py
│   ├── test_stock_api.py
│   ├── test_stock_detail_api.py
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
├── requirements-dev.txt
└── ruff.toml
```

Not in Git (local only, on purpose): `.env` (real secrets), `.venv/` (installed packages).

## `app/` — the application

| File | Contains | Phase |
|---|---|---|
| `__init__.py` | Empty. Makes `app` a Python package. | 0 |
| `main.py` | Creates the FastAPI app, includes all routers, rate-limit handler (429), `StockConflict` → **409** and `NotFound` → **404** handlers, `GET /health`. `lifespan` starts the nightly scheduler when `SCHEDULER_ENABLED` is true and stops it on shutdown; logging set to INFO. Phase 8: security-headers middleware (strict CSP on everything except `/docs` and `/redoc`, plus `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`), `GET /` → redirect to `/app/`, `app/static` mounted at `/app` (last, so it can never shadow an API route), `.js`/`.css` MIME types pinned (Windows registry can say `text/plain`) | 0–8 |
| `config.py` | `Settings`: reads `DATABASE_URL` and `JWT_SECRET` from environment / `.env`; normalises Railway's `postgresql://` to `postgresql+psycopg://`; `scheduler_enabled` (default **false**, so tests never start a background thread) | 0, 7 |
| `database.py` | `engine` (connection pool, `pool_pre_ping`), `SessionLocal`, `Base` (parent of all models), `get_db()` (one session per request, always closed) | 0 |
| `security.py` | `hash_password`, `verify_password` (bcrypt), `create_access_token`, `decode_access_token` (JWT, HS256, 60 min), `DUMMY_HASH` (timing protection) | 1 |
| `dependencies.py` | `get_current_user` (token → user from DB, else **401**), `require_roles(...)` (wrong role → **403**) | 1 |
| `pagination.py` | `Paging` dependency (`limit` 1–200, default 50; `offset` ≥ 0 → **422** otherwise) and the generic `Page[T]` response: `{items, total}` | 5 |
| `rate_limit.py` | The shared slowapi `limiter` (login: 5 per minute per IP) | quality |
| `scheduler.py` | `create_scheduler()` (APScheduler, job `low_stock_check` every night at **02:00 UTC**, `max_instances=1`, `coalesce`), `nightly_low_stock_job()` (own session, logs the result, logs errors instead of raising) | 7 |
| `seed.py` | Creates the first admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME`. Idempotent. Run with `py -m app.seed`. | 1 |

### `app/models/` — database tables (SQLAlchemy)

| File | Contains |
|---|---|
| `__init__.py` | Exports all models and enums (`Inventory`, `Location`, `MovementType`, `Notification`, `Product`, `ProductUnit`, `StockMovement`, `User`, `UserRole`). Alembic imports this to see all tables |
| `user.py` | `UserRole` enum (admin / worker / planner) and the `User` table: id, name, email (unique), password_hash, role (CHECK), is_active, created_at |
| `product.py` | `ProductUnit` enum (pcs / box / kg) and the `Product` table: id, sku (unique), name, unit (CHECK), reorder_point (CHECK ≥ 0), is_active, low_stock_alerted, created_at |
| `location.py` | `Location` table: id, code (unique, CHECK format `A-01-03`), description (optional), is_active |
| `notification.py` | `Notification` table — one message for one user: user_id (FK), title (≤ 200), body, created_at, read_at (`NULL` = unread). Index on (user_id, read_at) |
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
| `stock.py` | `StockSummary` (per product: total, reorder point, `below_reorder`), `ProductStock` (summary + `locations`), `LocationQuantity`, `ShelfItem` |
| `notification.py` | `NotificationOut`: id, title, body, created_at, read_at |
| `planner.py` | `PlannerRow`: total, reorder point, `below_reorder`, `used_last_30_days`, `avg_daily_usage`, `days_left` (null when no usage) |
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
| | `GET /locations/{id}/stock` — products on this shelf (quantity > 0) | any logged-in user |
| | `POST /locations`, `PATCH /locations/{id}` (deactivating a location that holds stock → **409**) | admin |
| `movements.py` | `POST /movements/receive`, `/pick`, `/move`, `/adjust` — each returns **201** with the movement and new stock per location | admin, worker |
| | `GET /movements` (filters: product, location, type, user, date range; newest first; paginated), `GET /movements/{id}` | any logged-in user |
| `stock.py` | `GET /stock?search=&below_reorder=` (paginated), `GET /stock/{product_id}` | any logged-in user |
| `planner.py` | `GET /planner?only_below=&sort=days_left\|sku` (paginated) | any logged-in user |
| `notifications.py` | `GET /notifications?unread=` (own only, newest first, paginated), `POST /notifications/{id}/read` (someone else's → **404**) | admin, planner |

### `app/services/` — business logic (no HTTP)

| File | Contains |
|---|---|
| `__init__.py` | Empty |
| `stock.py` | `increase_stock` (upsert: `INSERT … ON CONFLICT DO UPDATE`), `decrease_stock` (locks the row with `SELECT … FOR UPDATE`, rejects missing / insufficient stock), `lock_stock_rows` (locks several rows, lowest `location_id` first, so moves can't deadlock), `StockConflict` (→ 409). Never commits. |
| `overview.py` | `stock_summaries` (LEFT JOIN + SUM + GROUP BY, active products only, `HAVING` for `below_reorder`, count + page), `product_stock`, `location_stock` (quantity > 0 only) |
| `history.py` | `movement_history` (optional filters, dates are whole UTC days, `ORDER BY created_at DESC, id DESC`), `get_movement` |
| `planner.py` | `planner_rows`: stock and 30-day pick usage summed in **separate subqueries** (avoids fan-out), `days_left = total × 30 / used` computed in SQL so the database can sort by it (`NULLS LAST`) |
| `alerts.py` | `run_low_stock_check` — the nightly job: new low products (not yet flagged) → one notification per active admin and planner + set `low_stock_alerted`; restocked products → clear the flag; nobody to notify → nothing flagged; one transaction, rollback on any error. Returns `LowStockResult` |
| `notifications.py` | `my_notifications` (filter on `user_id`, optional unread), `mark_as_read` (sets `read_at` once; looks up by id **and** user, so foreign ids behave like missing ones → `NotFound`) |
| `movements.py` | `receive`, `pick`, `move`, `adjust`: check product/location exist and are active (`NotFound` → 404, `StockConflict` → 409), lock and change stock, record the movement, **one commit**. `_all_or_nothing` rolls back on any error. |

Rule: routers handle HTTP (schemas, roles, status codes); services handle the warehouse rules. Services can be tested without HTTP.

### `app/static/` — the frontend (Phase 8)

Plain HTML, CSS and JavaScript modules. No build step, no framework, same origin as the API (no CORS).

| Page | For | What it does |
|---|---|---|
| `index.html` | everyone | Login. Stores the JWT in `sessionStorage`, then goes to the role's start page (admin → stock, worker → operations, planner → planner) |
| `stock.html` | all | Stock overview: search, "only below reorder point", paginated |
| `product.html?id=` | all | One product: totals, stock per location, last 10 movements; reorder-point form for admin + planner; quick links to operations for admin + worker |
| `operations.html` | admin, worker | Receive / pick / move / adjust in one form. "From" only lists locations holding the product, with quantities. Clear 409 / 422 messages. Prefills from `?type=&product=&from=` |
| `history.html` | all | Movement history with every API filter (user filter for admins only, since only admins can list users); filters kept in the URL |
| `planner.html` | all | Usage, per-day average, days left with a small gauge, below-reorder status |
| `notifications.html` | admin, planner | Inbox, unread filter, mark as read (updates the menu badge) |
| `shelf.html?id=` | all | What is on one location; printable count sheet with a blank "Counted" column; link to record a count difference |
| `products.html`, `locations.html`, `users.html` | admin | Create + edit (in a `<dialog>`), activate / deactivate. Own role/active can't be changed (API returns 409 anyway) |

| Script | Contains |
|---|---|
| `js/api.js` | `api()` — adds the token, turns errors into readable text (422 field list, 409 detail, 403/429/5xx messages), **401 → back to login**; `apiAll()` for paginated lists |
| `js/dom.js` | `el()` builds elements; text only via `textContent`. Helpers for tables, selects, pager, messages, dialogs, number/date formatting |
| `js/layout.js` | `startPage({roles})`: checks login with `/auth/me`, draws the role-based menu, unread badge (`/notifications?unread=true&limit=1` → `total`), logout; shows "No access" if the role doesn't match |
| `js/lookups.js` | Loads products / locations / users into id maps; `movementRow()` shared by history, product and operations pages |

Security rules (checked by `tests/test_frontend.py`):
- CSP `script-src 'self'; style-src 'self'` → no inline `<script>`, no `onclick=`, no `style=` in any page.
- No `innerHTML` / `outerHTML` / `insertAdjacentHTML` / `document.write` / `eval` in any script: API data can never become HTML.
- Hiding a menu item is only convenience. The backend's 403 is the real block.
- Token in `sessionStorage`, not a cookie → no CSRF; it disappears when the tab closes. Logout only forgets the token (it stays valid until it expires, see known gaps).

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
| `versions/1dfb42dda5bc_…` | Migration 5: `notifications` table, FK to users, index on (user_id, read_at) |

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
| `test_stock_api.py` | `GET /stock`: login required, all roles, totals over locations, zero stock, `below_reorder`, sorted, inactive hidden, filters, search, pagination + total, invalid paging 422 |
| `test_stock_detail_api.py` | `GET /stock/{id}` and `GET /locations/{id}/stock`: per-location breakdown sorted by code, zero rows hidden, unknown id 404 |
| `test_movement_history_api.py` | `GET /movements`: newest first with id tie-break, every filter, whole-day date range, combined filters, pagination, invalid query 422; `GET /movements/{id}` 200 / 401 / 404 |
| `test_planner_api.py` | usage = picks in the last 30 days only (old picks and receive / move / adjust ignored), avg and days left, null when unused, inactive hidden, sort by days left (nulls last) or SKU, `only_below`, pagination, invalid query 422 |
| `test_notification_model.py` | unread + timestamped by default, user required and must exist, title and body required, title ≤ 200, the (user_id, read_at) index exists |
| `test_low_stock_job.py` | one notification per active admin/planner, message lists every low product, flags set, second run no duplicates, restock clears the flag, low again alerts again, inactive products ignored, no recipients → no flags, failure saves nothing |
| `test_notifications_api.py` | login required, workers 403, only own notifications, newest first, unread/read filter, pagination, mark as read, second read keeps first time, someone else's or unknown id → 404 |
| `test_scheduler.py` | job runs at 02:00 UTC, opens its own session, errors are logged not raised, scheduler starts and stops with the app when enabled, stays off otherwise, off by default |
| `test_frontend.py` | `/` redirects to `/app/`, pages and JS/CSS served with the right types, security headers present (no CSP on `/docs`), every page exists, has no inline JS/CSS and only loads scripts that exist, no script builds HTML from strings |
| `e2e/test_smoke.py` | Real browser (Playwright + Chromium) against the app running in a thread on the test DB: login and wrong password, worker picks stock and sees the 409, worker blocked from admin page, planner changes a reorder point, admin adds a location, logout. Fails on any JS error or CSP violation. Skipped if Playwright is not installed |
| `test_concurrency.py` | two threads with separate sessions run at the same moment (a `Barrier` forces the overlap): two picks of the last item → one ok + one conflict, stock 0, one movement; opposite moves A→B and B→A → both ok, no deadlock, correct totals |

Run with `py -m pytest -v` (needs the database: `docker compose up -d db`). 316 tests.
For the browser tests: `py -m pip install -r requirements-dev.txt` and `py -m playwright install chromium` once.

Phases 3–8 were built test-first (red → green): each test was seen failing before the code existed.

## `docs/` — design documents

| File | Contains |
|---|---|
| `project-brief.md` | Problem, users, MVP, out of scope, phases, success criteria |
| `data-model.md` | All tables, constraints, movement rules, notifications |
| `api-endpoints.md` | All planned endpoints with roles and status codes |
| `transaction-flows.md` | Transaction steps for receive / pick / move / adjust (implemented in Phases 3–4) and the nightly low-stock job (Phase 7) |
| `project-structure.md` | This file |

## Root — infrastructure and config

| File | Contains |
|---|---|
| `Dockerfile` | Python 3.14-slim → install requirements → copy `alembic/` and `app/` → `alembic upgrade head && uvicorn` on `${PORT:-8000}` |
| `docker-compose.yml` | `db` (Postgres 17, healthcheck, `pgdata` volume, host port **5433** because a Windows PostgreSQL uses 5432) + `api` (waits for healthy db, `DATABASE_URL` uses host `db`, `SCHEDULER_ENABLED: "true"`) |
| `.github/workflows/ci.yml` | On every push and PR: Postgres service → install `requirements-dev.txt` + Chromium → Ruff lint + format check → migrate → pytest (incl. browser tests) |
| `ruff.toml` | Ruff rules (E, F, I, B, UP, S), line length 100, `app` first-party, migrations excluded |
| `requirements.txt` | Pinned packages for the app (what the Docker image installs) |
| `requirements-dev.txt` | `-r requirements.txt` + Playwright for browser tests. Not in the Docker image |
| `.env.example` | Variable names with placeholder values (committed), including `SCHEDULER_ENABLED=false` |
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
