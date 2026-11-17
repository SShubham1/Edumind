import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, SessionLocal, engine
from .routers import flashcards, health, records, students, topics
from .seed import seed_demo_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            created = seed_demo_data(db)
            if created:
                logger.info("Seeded demo students, topics and quiz history.")
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Adaptive learning platform API. Cross-dev plugin endpoints are intentionally "
        "not implemented yet; they will be added with the HomeSolar collaboration."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(topics.router)
app.include_router(students.router)
app.include_router(records.router)
app.include_router(flashcards.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health",
    }
