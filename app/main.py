import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
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
