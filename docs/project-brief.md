# Smart Warehouse Management — Project Brief

## 1. Problem

Small warehouses often track stock in spreadsheets or on paper. The numbers drift away from reality, nobody can see who moved what or when, and products run out without warning because no one noticed they were getting low.

## 2. Users

| Role | Who | What they need |
|---|---|---|
| Admin | Warehouse manager | Manage users, products, locations; see everything |
| Warehouse worker | People on the floor | Receive, pick, move and count stock quickly and correctly |
| Planner | Person responsible for reordering | Know what is running low and how long stock will last |

## 3. Solution

A web application that records every stock change as a movement, always knows how much of each product is in each location, prevents impossible operations such as negative stock, and warns automatically when products need reordering.

## 4. MVP features

### 4.1 Products
SKU (unique), name, unit (`pcs`, `box`, `kg`), reorder point, active status, created timestamp.
Products with history are deactivated, never deleted.

### 4.2 Locations
One warehouse. Locations use the code format `A-01-03` (aisle A, rack 01, shelf 03).
A product can be stored in several locations, and a location can hold several products.

### 4.3 Stock movements
Every change to stock is a permanent record. Four types:

| Type | Meaning | Example |
|---|---|---|
| Receive | Goods arrive | +200 cables to A-01-03 |
| Pick | Goods leave for an order | −5 cables from A-01-03 |
| Move | Between locations | 40 from A-01-03 to B-02-01 |
| Adjust | Correction after a count | −2 after counting; **reason required** |

Each movement stores product, quantity, from/to location, type, user, timestamp and reason.
Movements are never edited or deleted; corrections are new movements.

### 4.4 No negative stock
Stock can never go below zero, including when two users pick the last item at the same time.
Implemented with a database transaction that updates `inventory` and inserts the movement atomically, row locking on the inventory row, and a `CHECK (quantity >= 0)` constraint as a final safety net.

### 4.5 Stock overview
Total per product, breakdown per location, search by SKU or name, and movement history with filters.

### 4.6 Light planner (the "smart" part)
Calculated from movement history:
- **Average daily usage** — picks over the last 30 days ÷ 30
- **Days of stock left** — current stock ÷ average daily usage
- **Below reorder point** — products under their reorder point

### 4.7 Roles and permissions

| Action | Admin | Worker | Planner |
|---|---|---|---|
| Manage users | ✅ | | |
| Create/edit products and locations | ✅ | | |
| Change reorder points | ✅ | | ✅ |
| Receive, pick, move | ✅ | ✅ | |
| Adjust stock | ✅ | ✅ | |
| View stock, history, planner | ✅ | ✅ | ✅ |

Permissions are enforced in the backend, not only hidden in the interface.

### 4.8 Nightly low-stock alert
A scheduled background job runs every night, finds active products below their reorder point, and creates one in-app notification summarising them. A product is not alerted again until it has been restocked above its reorder point.

## 5. Out of scope (version 1)

- Suggested order quantities and forecasting
- Purchase orders and suppliers
- Multiple warehouses
- Barcode scanning
- Shipping, invoicing, accounting
- Email notifications (in-app only to start)

## 6. Technology

| Area | Choice |
|---|---|
| Language / framework | Python, FastAPI |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| Auth | JWT, bcrypt, role-based access |
| Background jobs | Scheduled worker for nightly alerts |
| Frontend | HTML, CSS, JavaScript |
| Testing | pytest, against a real PostgreSQL for concurrency tests |
| Containers | Docker, Docker Compose |
| CI | GitHub Actions on every push |
| Hosting | Linux-based platform (e.g. Railway) |

## 7. Main tables

`users`, `products`, `locations`, `inventory` (current quantity per product per location), `stock_movements` (full history), `notifications`.

## 8. Development plan

Each phase is built on its own branch, with tests written alongside the code, and merged through a pull request once CI is green.

| Phase | Goal | Done when |
|---|---|---|
| **0. Foundation** | Repo, project structure, Docker Compose (API + PostgreSQL), Alembic, CI pipeline, `.env.example` | `docker compose up` runs a hello endpoint; CI green |
| **1. Auth and roles** | Users, login with JWT, three roles, permission checks; first admin created by a seed script | Tests prove each role can only do its allowed actions |
| **2. Products and locations** | Create, list, edit, deactivate; SKU unique; location code format validated | Tests for validation and permissions |
| **3. Stock movements** | Receive, pick, move, adjust; inventory and movement written in one transaction; reason required for adjust | Every operation creates a movement with user and timestamp |
| **4. Concurrency** | Row locking + CHECK constraint | A test runs two simultaneous picks of the last item; exactly one succeeds |
| **5. Stock overview** | Totals, per-location breakdown, search, filtered and paginated history | Overview matches the sum of movements |
| **6. Light planner** | Daily usage, days left, below-reorder list | Tests with known movement data give the expected numbers |
| **7. Nightly alerts** | Scheduled job, notifications table, no duplicate alerts | Job tested by calling it directly; duplicates prevented |
| **8. Frontend** | Pages for workers (stock operations), planners (planner view), admins (management) | Each role can do its job in the browser |
| **9. Deploy and finish** | Production deploy, logs, README, demo accounts per role, portfolio entry, retrospective | Live link works for all three demo roles |

## 9. Success criteria

- Two simultaneous picks of the last item never produce negative stock, proven by a test
- Every stock change has a movement record with user, time and, for adjustments, a reason
- Role permissions are covered by tests
- CI green on every push; the full system runs with `docker compose up`
- Deployed live, with a demo account for each role

## 10. Learning goals

- Relational data modelling with several related tables
- Database transactions, row locking and constraints
- Analytics queries over time-based data
- Scheduled background jobs
- Role-based authorization in a multi-role system
- Testing concurrency against a real database
- A professional workflow: branches, pull requests, CI, Docker from day one