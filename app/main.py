from fastapi import FastAPI

from app.routers import auth, locations, products, users

app = FastAPI(title="Smart Warehouse Management")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(locations.router)


@app.get("/health")
def health():
    return {"status": "ok"}
