from fastapi import FastAPI

app = FastAPI(title="Smart Warehouse Management")


@app.get("/health")
def health():
    return {"status": "ok"}