import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.rate_limit import limiter
from app.routers import (
    auth,
    locations,
    movements,
    notifications,
    planner,
    products,
    stock,
    users,
)
from app.scheduler import create_scheduler
from app.services.movements import NotFound
from app.services.stock import StockConflict

# Browsers refuse ES module scripts with the wrong MIME type. On Windows the registry can map
# .js to text/plain, so pin the types instead of trusting the operating system.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Strict policy for the frontend: only our own files, no inline scripts or styles, no framing.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
# Swagger UI / ReDoc use inline scripts and a CDN, so they get the basic headers but no CSP.
DOCS_PATHS = ("/docs", "/redoc")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the nightly scheduler with the app, and stop it when the app stops."""
    scheduler = create_scheduler() if settings.scheduler_enabled else None
    if scheduler:
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Smart Warehouse Management", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith(DOCS_PATHS):
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    return response


@app.exception_handler(StockConflict)
def stock_conflict_handler(request: Request, exc: StockConflict) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(NotFound)
def not_found_handler(request: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(locations.router)
app.include_router(movements.router)
app.include_router(stock.router)
app.include_router(planner.router)
app.include_router(notifications.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")


# Mounted last and under /app, so the frontend can never shadow an API route.
app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="static")
