# Deploying to Railway

The app is one Docker container plus one PostgreSQL database. Railway builds the container from
the `Dockerfile`; `railway.json` sets the health check (`/health`) and keeps it at **one replica**
(the nightly job and the rate-limit counters live in the process).

On start the container runs `alembic upgrade head`, then uvicorn on Railway's `$PORT` with
`--proxy-headers`.

## 1. Create the project

1. <https://railway.com> → **New Project** → **Deploy from GitHub repo** → `smart-warehouse-management`.
2. In the same project: **+ New** → **Database** → **PostgreSQL**.
3. Don't worry if the first app deploy fails: its variables aren't set yet.

## 2. Set the app's variables

App service → **Variables** → **Raw Editor**, paste, then fill in `JWT_SECRET`:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
JWT_SECRET=<64 hex characters, see below>
SCHEDULER_ENABLED=true
TRUST_PROXY_HEADERS=true
FORWARDED_ALLOW_IPS=*
DEMO_MODE=true
```

Generate the secret locally (never reuse the one in your `.env`):

```powershell
py -c "import secrets; print(secrets.token_hex(32))"
```

| Variable | Why |
|---|---|
| `DATABASE_URL` | Railway's reference to the Postgres service. Its `postgresql://` is switched to the psycopg driver in `app/config.py` |
| `JWT_SECRET` | Signs login tokens. The app refuses to start with fewer than 32 characters |
| `SCHEDULER_ENABLED` | Runs the 02:00 UTC low-stock check |
| `TRUST_PROXY_HEADERS` | Rate-limit on the real client IP (last `X-Forwarded-For` hop), not Railway's proxy IP |
| `FORWARDED_ALLOW_IPS` | Read by uvicorn: trust `X-Forwarded-Proto` from Railway's proxy, so HTTPS is detected (HSTS) |
| `DEMO_MODE` | Public demo: demo logins on the login page, demo data loaded into the empty database on first start and reset every night at 03:00 UTC. **Leave it out for a real warehouse** |

## 3. Get a public address

App service → **Settings** → **Networking** → **Generate Domain**. Railway serves it over HTTPS.

## 4. Check it

1. **Deployments** → latest → logs end with `Application startup complete` (in demo mode also `Demo data loaded into the empty database`).
2. `https://<your-domain>/health` → `{"status":"ok"}`.
3. Open `https://<your-domain>/` → log in with each demo button.
4. Run the rate-limit check from [security-review.md](security-review.md#needs-validation-after-deploy): 5 × 401, then 429.

## Without demo mode (a real warehouse)

Remove `DEMO_MODE`, then create the first admin once, inside the running app container
(where `DATABASE_URL` points at the private Postgres address), using the
[Railway CLI](https://docs.railway.com/guides/cli):

```powershell
railway ssh --service <app-service>
# inside the container:
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='a-long-password' python -m app.seed
```

The seed is idempotent: running it again changes nothing.

## Updating

Every push to `main` redeploys. Migrations run automatically on start; a failed migration stops
the new deploy and Railway keeps the previous one running.
