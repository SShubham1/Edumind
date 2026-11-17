"""Subjects and topic provenance.

A subject is a curriculum domain declared by content. Subjects are **created by
content**, never pre-populated: an importer, API client or plugin creates its
own subject when it declares topics. This keeps the subject list honest: if it
appears in the UI, something actually put content there.

The ASSISTments Skill Builder CSV has no subject field, so the importer does not
assign one. Imported topics stay subject-less until an importer that actually
declares a subject attaches them to one.

``SUBJECT_REGISTRY`` only holds display metadata for keys a plugin or API client
may declare, so the UI gets a proper name instead of a slug. It is never used to
create a subject on its own.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import ProblemResponse, Subject, Topic

SUBJECT_REGISTRY: dict[str, tuple[str, str]] = {
    "computer-science": (
        "Computer Science",
        "Algorithms, data structures and computing fundamentals.",
    ),
    "trading": (
        "Trading",
        "Financial-market concepts such as moving averages and risk management.",
    ),
}


def ensure_subject(db: Session, key: str) -> Subject:
    """Return the subject for ``key``, creating it if needed.

    Called only by content producers (ETL, API clients, plugin registration),
    never by the API on startup.
    """
    normalised = key.strip().casefold()
    subject = db.scalar(select(Subject).where(Subject.key == normalised))
    if subject is not None:
        return subject

    name, description = SUBJECT_REGISTRY.get(
        normalised, (normalised.replace("-", " ").title(), None)
    )
    subject = Subject(key=normalised, name=name, description=description)
    db.add(subject)
    db.flush()
    return subject


def resolve_subject(db: Session, value: str | int) -> Subject:
    """Resolve a subject by key, name or numeric id.

    Accepts a string so API callers can use ``?subject=trading`` and
    ``?subject=Trading`` interchangeably.
    """
    if isinstance(value, int) or str(value).isdigit():
        subject = db.get(Subject, int(value))
        if subject is not None:
            return subject
        raise ValueError(f"Unknown subject id {value!r}.")

    needle = str(value).strip()
    subject = db.scalar(
        select(Subject).where(
            (func.lower(Subject.key) == needle.casefold())
            | (func.lower(Subject.name) == needle.casefold())
        )
    )
    if subject is None:
        raise ValueError(f"Unknown subject {value!r}.")
    return subject


def resolve_or_register_subject(db: Session, value: str | int) -> Subject:
    """Resolve a subject, creating it when ``value`` is a known registry key.

    Used by ``POST /api/topics`` so callers can add content to a known domain
    (e.g. ``computer-science`` or ``trading``) without a separate registration
    step, while an arbitrary unknown subject still returns 404.
    """
    try:
        return resolve_subject(db, value)
    except ValueError:
        if isinstance(value, str) and value.strip().casefold() in SUBJECT_REGISTRY:
            return ensure_subject(db, value)
        raise


def backfill_topic_sources(db: Session) -> int:
    """Label provenance for topics created before the ``source`` column.

    The dataset name is copied from the topic's imported responses. No subject
    is inferred: a dataset that declares no subject (ASSISTments) leaves its
    topics unassigned rather than inventing a curriculum label.
    """
    updated = 0
    topics = db.scalars(
        select(Topic).where(
            (Topic.source.is_(None))
            | (Topic.source == "")
            | (Topic.source == "curated")
        )
    ).all()
    for topic in topics:
        dataset = db.scalar(
            select(ProblemResponse.source)
            .where(ProblemResponse.topic_id == topic.id)
            .limit(1)
        )
        if dataset:
            topic.source = dataset
            updated += 1

    if updated:
        db.flush()
    return updated
