"""CreatorLab backend — Sprint 0.1 foundation. Serves GET /health."""
from fastapi import FastAPI

app = FastAPI(title="CreatorLab", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "creatorlab", "version": "0.1.0"}
