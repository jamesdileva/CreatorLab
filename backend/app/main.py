"""CreatorLab backend — Sprint 1.1: health + creator CRUD."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.creators import router as creators_router
from .api.episodes import router as episodes_router
from .api.simulation import router as simulation_router
from .core.database import Base, engine
from .models import creator as _creator_model  # noqa: F401  (register tables)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="CreatorLab", version="0.1.1", lifespan=lifespan)
app.include_router(creators_router)
app.include_router(episodes_router)
app.include_router(simulation_router)

# Dev-only media serving so rendered artifacts are previewable in the UI.
Path("media/generated").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "creatorlab", "version": "0.1.1"}
