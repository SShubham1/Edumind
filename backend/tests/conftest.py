import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import Base


@pytest.fixture(autouse=True)
def _disable_llm(monkeypatch):
    """Keep tests hermetic and free of real provider calls.

    A developer machine may have a working ``LLM_API_KEY`` in ``.env``; tests
    must not make network requests or depend on that key. Tests that need an
    LLM response patch the relevant function explicitly.
    """
    monkeypatch.setattr(settings, "llm_api_key", None)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestingSession() as session:
        yield session
    engine.dispose()
