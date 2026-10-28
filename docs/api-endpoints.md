# API Endpoints — smart-warehouse-management

Design & Planning document. Source of truth for routes, roles and error codes.
Related: [data-model.md](data-model.md), [transaction-flows.md](transaction-flows.md).

## 1. Design rules

| Rule | Reason |
|---|---|
| URLs are nouns, HTTP methods are verbs | Predictable REST; readable in `/docs` |
| No `DELETE` for users, products, locations or movements | History is never deleted; deactivate with `PATCH` instead |
| No `PUT` / `PATCH` / `DELETE` on movements | Movements are immutable; corrections are new adjust movements |
| Lists take `limit` (default 50, max 200) and `offset`, and return `{ "items": [...], "total": n }` | Movement history grows forever |
| Permissions enforced per route with a dependency, e.g. `require_roles("admin", "worker")` | Enforced in the backend, visible on each route |
| SKU and unit are not editable after creation | Changing them would silently change the meaning of history |

## 2. Status codes

| Code | When |
|---|---|
| `200` | OK |
| `201` | Created |
| `401` | Not logged in / invalid or expired token |
| `403` | Logged in, but role not allowed |
| `404` | Resource not found (or not owned, for notifications) |
| `409` | Valid request that conflicts with current state (see §5) |
| `422` | Invalid input (Pydantic validation, see §5) |
| `429` | Too many login attempts (rate limit) |

Rule of thumb: **422 = the request itself is wrong. 409 = the request is fine, but the database state says no.**

Error body (FastAPI default): `{ "detail": "Insufficient stock: 3 available, 5 requested" }`

## 3. Endpoints

Roles: **A** = admin, **W** = worker, **P** = planner. "all" = any logged-in user.

### Auth & health

| Method | Path | Roles | Notes | Phase |
|---|---|---|---|---|
| GET | `/health` | public | Docker / Railway health check | 0 |
| POST | `/auth/login` | public | Body: `email`, `password`. Returns JWT. Rate-limited 5/min per IP. Inactive user → `401` | 1 |
| GET | `/auth/me` | all | `id`, `name`, `email`, `role` | 1 |

### Users

| Method | Path | Roles | Notes | Phase |
|---|---|---|---|---|
| GET | `/users` | A | | 1 |
| POST | `/users` | A | Body: `name`, `email`, `password`, `role`. Duplicate email → `409` | 1 |
| PATCH | `/users/{id}` | A | `name`, `role`, `is_active`, `password`. No delete (movements reference users) | 1 |

Password is never returned in any response.

### Products

| Method | Path | Roles | Notes | Phase |
|---|---|---|---|---|
| GET | `/products?search=&active=` | all | Search on SKU or name | 2 |
| POST | `/products` | A | `sku`, `name`, `unit`, `reorder_point`. Duplicate SKU → `409` | 2 |
| GET | `/products/{id}` | all | | 2 |
| PATCH | `/products/{id}` | A | `name`, `is_active` only. SKU and unit are not accepted | 2 |
| PATCH | `/products/{id}/reorder-point` | A, P | Body: `reorder_point` (≥ 0) | 2 |

### Locations

| Method | Path | Roles | Notes | Phase |
|---|---|---|---|---|
| GET | `/locations?active=` | all | | 2 |
| POST | `/locations` | A | `code` must match `^[A-Z]-\d{2}-\d{2}$`. Duplicate → `409` | 2 |
| GET | `/locations/{id}` | all | | 2 |
| PATCH | `/locations/{id}` | A | `is_active`. Deactivating while it holds stock → `409` | 2 |

### Stock movements

| Method | Path | Roles | Body | Phase |
|---|---|---|---|---|
| POST | `/movements/receive` | A, W | `product_id`, `to_location_id`, `quantity`, `reason?` | 3 |
| POST | `/movements/pick` | A, W | `product_id`, `from_location_id`, `quantity`, `reason?` | 3 |
| POST | `/movements/move` | A, W | `product_id`, `from_location_id`, `to_location_id`, `quantity`, `reason?` | 3 |
| POST | `/movements/adjust` | A, W | `product_id`, `location_id`, `quantity_change` (signed, ≠ 0), `reason` (required) | 3 |
| GET | `/movements?product_id=&location_id=&type=&user_id=&date_from=&date_to=&limit=&offset=` | all | Newest first | 5 |
| GET | `/movements/{id}` | all | | 5 |

All four POSTs return `201` with the created movement **and** the new quantity at each affected location:

```json
{
  "movement": { "id": 42, "type": "pick", "product_id": 7, "from_location_id": 3,
                "to_location_id": null, "quantity": 5, "user_id": 2,
                "reason": null, "created_at": "2026-10-28T21:15:00Z" },
  "inventory": [ { "location_id": 3, "quantity": 195 } ]
}
```

Adjust translation (API is friendly, DB stays strict):

| API input | Stored movement |
|---|---|
| `location_id: 3, quantity_change: -2` | `from_location_id = 3, to_location_id = NULL, quantity = 2` |
| `location_id: 3, quantity_change: +2` | `from_location_id = NULL, to_location_id = 3, quantity = 2` |

### Stock overview

| Method | Path | Roles | Notes | Phase |
|---|---|---|---|---|
| GET | `/stock?search=&below_reorder=` | all | Per product: `total`, `reorder_point`, `below_reorder` | 5 |
| GET | `/stock/{product_id}` | all | Total + breakdown per location (quantity > 0 only) | 5 |
| GET | `/locations/{id}/stock` | all | All products on this shelf (used when counting) | 5 |

### Planner

| Method | Path | Roles | Notes | Phase |
|---|---|---|---|---|
| GET | `/planner?only_below=&sort=days_left` | all | Per product: `total`, `reorder_point`, `avg_daily_usage`, `days_left` (`null` when no usage) | 6 |

### Notifications

| Method | Path | Roles | Notes | Phase |
|---|---|---|---|---|
| GET | `/notifications?unread=` | A, P | Only the current user's (`user_id = current_user.id`) | 7 |
| POST | `/notifications/{id}/read` | A, P | Sets `read_at = now()` if NULL. Another user's notification → `404` | 7 |

Why `404` and not `403` for someone else's notification: `403` confirms the ID exists. `404` leaks nothing.

**Total: 27 endpoints.**

## 4. Not an endpoint

The nightly low-stock job is a plain function, `run_low_stock_check(db)`. A scheduler calls it, and tests call it directly. It is not exposed over HTTP, so nobody can trigger it from outside.

## 5. Validation and conflict rules

### 422 — invalid input (Pydantic, before touching the database)

| Rule | Endpoint(s) |
|---|---|
| `quantity` must be an integer > 0 | receive, pick, move |
| `quantity_change` must be ≠ 0 | adjust |
| `reason` required and non-empty (after trimming) | adjust |
| `from_location_id` = `to_location_id` | move |
| Location code does not match `A-01-03` format | POST /locations |
| `unit` not in `pcs`, `box`, `kg` | POST /products |
| `reorder_point` < 0 | products |
| Unknown field (`extra="forbid"`), e.g. `sku` in PATCH /products | PATCH routes |

### 409 — conflict with current state (checked inside the transaction)

| Rule | Endpoint(s) |
|---|---|
| Product is inactive | all movement POSTs |
| Location (from or to) is inactive | all movement POSTs |
| No inventory row for product at the from-location | pick, move, negative adjust |
| Not enough stock at the from-location | pick, move, negative adjust |
| `CHECK (quantity >= 0)` violated (safety net) | all movement POSTs |
| Duplicate SKU / location code / email | create routes |
| Deactivating a location that holds stock | PATCH /locations/{id} |

### 404

Product or location ID does not exist (movement POSTs, GET by id).

## 6. Permission matrix → endpoints (for tests)

| Action (brief §4.7) | Endpoints | A | W | P |
|---|---|---|---|---|
| Manage users | `/users*` | ✅ | 403 | 403 |
| Create/edit products and locations | POST/PATCH `/products`, `/locations` | ✅ | 403 | 403 |
| Change reorder points | PATCH `/products/{id}/reorder-point` | ✅ | 403 | ✅ |
| Receive, pick, move, adjust | POST `/movements/*` | ✅ | ✅ | 403 |
| View stock, history, planner | GET `/products`, `/locations`, `/stock`, `/movements`, `/planner` | ✅ | ✅ | ✅ |
| Notifications | `/notifications*` | ✅ | 403 | ✅ |

Each ❌ cell becomes one parametrized pytest case asserting `403`.
