# Security Review — before the first public deploy (Phase 9)

Scope: `app/` (auth, roles, every router and service), the frontend in `app/static/`, `Dockerfile`,
`.github/workflows/ci.yml`, demo mode. Source review plus local tests only; nothing deployed was probed.
Date: 2026-11-11.

## Fixed in this phase

| # | Finding | Severity | Fix | Test |
|---|---|---|---|---|
| 1 | **Login rate limit unusable behind a proxy.** Behind Railway every request has the proxy's IP, so 5 wrong logins by anyone would lock out everyone; and trusting the *first* `X-Forwarded-For` entry would let an attacker rotate fake IPs to skip the limit. | medium | `app/rate_limit.py`: with `TRUST_PROXY_HEADERS=true`, key on the **last** `X-Forwarded-For` hop (added by the proxy, not the client); otherwise the socket address | `tests/test_rate_limit.py` |
| 2 | **Unauthenticated 500 on login with a long non-ASCII password.** The schema allowed 72 *characters*, bcrypt allows 72 *bytes* and bcrypt 5 raises above that (`"é" * 72` = 144 bytes). Same on user create / password change. | low | `app/schemas/password.py`: reject > 72 UTF-8 bytes → 422 | `tests/test_password_limits.py` |
| 3 | **422 responses echoed the rejected input**, which can be a password. | low | `main.py`: custom 422 handler drops `input` / `ctx`, keeps `loc` / `msg` / `type` | `tests/test_password_limits.py` |
| 4 | **Weak `JWT_SECRET` accepted** (`.env.example` had `change-me`). A guessable secret lets anyone sign an admin token. | medium (config) | `config.py` refuses secrets shorter than 32 characters or containing `change-me`; the app won't start | `tests/test_config.py` |

## Hardening (no exploitable path found, added anyway)

- Container runs as a non-root user; `.dockerignore` keeps `.env`, `.git`, tests and caches out of the build.
- `Strict-Transport-Security` on HTTPS responses (uvicorn `--proxy-headers` makes the scheme correct behind Railway).
- CI token is read-only (`permissions: contents: read`).

## Checked and fine

- **Roles:** every route declares its roles with `require_roles(...)`; the user and role are loaded from the database on every request, so a role change or deactivation applies immediately. Covered by per-role tests.
- **JWT:** HS256 with the algorithm pinned on decode (no `alg: none` / confusion), `exp` enforced, 60 minutes.
- **Login:** same error and a dummy bcrypt check for unknown, wrong-password and inactive users (no account enumeration by message or timing).
- **Notifications:** looked up by id **and** owner; someone else's id behaves like a missing one (404).
- **SQL:** all queries are SQLAlchemy expressions with bound parameters. The one raw `TRUNCATE` (`app/demo.py`) uses table names from the model metadata, never input.
- **Frontend XSS:** API data only reaches the DOM via `textContent` / `createElement`; a test fails on `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` or `eval`. Strict CSP (`script-src 'self'; style-src 'self'`, no `unsafe-inline`, `frame-ancestors 'none'`), enforced by tests and the browser smoke test.
- **Token storage:** `sessionStorage`, never a cookie, so there is no CSRF surface.
- **Secrets:** none in the repository; `.env` is git- and docker-ignored.

## Needs validation after deploy

**Railway's `X-Forwarded-For`.** Finding 1 assumes Railway's edge appends the real client IP as the
**last** entry, and that the app can only be reached through that edge. This is outside the source.
Owner check after deploy (your own demo, wrong password, takes one minute):

```powershell
# 6 wrong logins, each with a different fake first hop. Expect 401 x5, then 429.
1..6 | % { curl.exe -s -o NUL -w "%{http_code} " -X POST https://<your-app>/auth/login `
  -H "Content-Type: application/json" -H "X-Forwarded-For: 10.0.0.$_" `
  -d '{\"email\":\"nobody@example.com\",\"password\":\"wrong\"}' }
```

If the 6th is **not** 429, the fake header reaches the key: stop and revisit `client_ip`.

## Accepted risks (documented on purpose)

| Risk | Why accepted |
|---|---|
| Logout only drops the token in the browser; a stolen token works until it expires (60 min) | Short expiry; XSS (the usual way to steal it) is designed out. A deny-list is listed as future work |
| Demo mode: the public demo admin can change demo passwords, deactivate demo users or add junk data | Chosen trade-off: everything is wiped and re-seeded every night at 03:00 UTC |
| Demo mode: only login is rate-limited, so a visitor could script many writes | Data is reset nightly; Railway usage limits cap the cost. Never run demo mode for a real warehouse |
| Rate-limit counters and the scheduler live in the process | One Railway instance. Two instances would mean two schedulers and separate counters |
| `/docs` is public and has no CSP | Swagger UI needs inline scripts; it only shows the API that the frontend already uses |
| `DeadlockDetected` would return 500, not 503 | The fixed lock order prevents it; covered by `tests/test_concurrency.py` |
