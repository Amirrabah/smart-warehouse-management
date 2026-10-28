# Data model

```mermaid
erDiagram
    users ||--o{ stock_movements : "performs"
    users ||--o{ notifications : "receives"
    products ||--o{ inventory : "stored as"
    locations ||--o{ inventory : "holds"
    products ||--o{ stock_movements : "moved"
    locations ||--o{ stock_movements : "from / to"

    users {
        int id PK
        string name
        string email UK
        string hashed_password
        string role
        bool is_active
        datetime created_at
    }
    products {
        int id PK
        string sku UK
        string name
        string unit
        int reorder_point
        bool is_active
        bool low_stock_alerted
        datetime created_at
    }
    locations {
        int id PK
        string code UK
        string description
        bool is_active
    }
    inventory {
        int id PK
        int product_id FK
        int location_id FK
        int quantity
        datetime updated_at
    }
    stock_movements {
        int id PK
        string type
        int product_id FK
        int from_location_id FK
        int to_location_id FK
        int quantity
        string reason
        int user_id FK
        datetime created_at
    }
    notifications {
        int id PK
        int user_id FK
        string title
        string body
        datetime created_at
        datetime read_at
    }
```

## Database rules

| Table | Rules |
|---|---|
| `users` | email `UNIQUE`; role `CHECK IN ('admin', 'worker', 'planner')` |
| `products` | sku `UNIQUE`; unit `CHECK IN ('pcs', 'box', 'kg')`; reorder_point `>= 0`; sku and unit not editable after creation |
| `locations` | code `UNIQUE`; format `A-01-03` validated in the API |
| `inventory` | `UNIQUE (product_id, location_id)`; `quantity >= 0`; rows at zero are kept |
| `stock_movements` | `quantity > 0`; type `CHECK IN ('receive', 'pick', 'move', 'adjust')`; from/to rules below |
| `notifications` | `user_id` required (FK to users); `read_at` empty means unread; index on `(user_id, read_at)` |

## Movement rules

Every movement has a positive quantity. The direction comes from the locations:
`from_location` is where stock is removed, `to_location` is where stock is added.

| Type | from | to | Reason |
|---|---|---|---|
| receive | — | required | optional |
| pick | required | — | optional |
| move | required | required (different from `from`) | optional |
| adjust | exactly one of from / to | | **required** |

Applying a movement: subtract from `from` if set, add to `to` if set.
`inventory` (current stock) and `stock_movements` (history) are always written in one transaction.

## Notifications

Notifications are per user. The nightly low-stock job creates one notification for each active admin and planner, so every person has their own inbox and marks their own notifications as read.

## Low-stock alerts

`products.low_stock_alerted` is set when an alert is sent. The same nightly job clears it once stock is back above the reorder point, so a product is not alerted twice for the same shortage, but alerts again if it runs low later.
