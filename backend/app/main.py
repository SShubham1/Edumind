import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import SessionLocal, engine
from .migrations import ensure_schema
from .routers import flashcards, health, records, students, subjects, topics
from .subjects import backfill_topic_subjects

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    applied = ensure_schema(engine)
    if applied:
        logger.info("Applied schema upgrades: %s", ", ".join(applied))
    # Legacy topics (imported before subjects existed) should appear in their
    # subject. Content itself only ever arrives through an importer, the API or
    # a plugin; the app never fabricates topics or students on startup.
    with SessionLocal() as db:
        backfilled = backfill_topic_subjects(db)
        db.commit()
        if backfilled:
            logger.info("Assigned a subject to %s existing topics.", backfilled)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Adaptive learning platform API: mastery tracking, explainable "
        "recommendations, subject-scoped dashboards and LLM-assisted study "
        "material."
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
app.include_router(subjects.router)
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
