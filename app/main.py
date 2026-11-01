from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.rate_limit import limiter
from app.routers import auth, locations, products, users

app = FastAPI(title="Smart Warehouse Management")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(locations.router)


@app.get("/health")
def health():
    return {"status": "ok"}
