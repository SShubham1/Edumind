"""Subjects and topic provenance.

A subject is a curriculum domain (Mathematics, Computer Science, Trading, ...).
Subjects are **created by content**, never pre-populated: the ASSISTments ETL
creates Mathematics, and an importer, API client or plugin creates its own
subject when it declares topics. This keeps the subject list honest: if it
appears in the UI, something actually put content there.

``SUBJECT_REGISTRY`` only holds display metadata for known keys so the UI and
API get a proper name instead of a slug when that content arrives.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import ProblemResponse, Subject, Topic

SUBJECT_REGISTRY: dict[str, tuple[str, str]] = {
    "mathematics": (
        "Mathematics",
        "Middle-school mathematics, including the imported ASSISTments history.",
    ),
    "computer-science": (
        "Computer Science",
        "Algorithms, data structures and computing fundamentals.",
    ),
    "trading": (
        "Trading",
        "Financial-market concepts such as moving averages and risk management.",
    ),
}

# Datasets whose responses are maths practice. Used to backfill the subject of
# topics that were imported before subjects existed.
_MATHS_DATASET_PREFIXES = ("assistments",)


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

    Accepts a string so API callers can use ``?subject=mathematics`` and
    ``?subject=Mathematics`` interchangeably.
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
    (e.g. ``mathematics`` or ``trading``) without a separate registration step,
    while an arbitrary unknown subject still returns 404.
    """
    try:
        return resolve_subject(db, value)
    except ValueError:
        if isinstance(value, str) and value.strip().casefold() in SUBJECT_REGISTRY:
            return ensure_subject(db, value)
        raise


def backfill_topic_subjects(db: Session) -> int:
    """Assign a subject and source to topics created before those columns.

    Rules:
    * topics with ASSISTments responses become Mathematics, labelled with the
      dataset name, so imported history is visibly distinct from curated data;
    * every other unlabelled legacy topic is attached to Computer Science,
      which is what the pre-subject demo database contained, and marked
      ``source="legacy"``.
    """
    updated = 0
    cache: dict[str, Subject] = {}
    topics = db.scalars(select(Topic).where(Topic.subject_id.is_(None))).all()
    for topic in topics:
        dataset = db.scalar(
            select(ProblemResponse.source)
            .where(ProblemResponse.topic_id == topic.id)
            .limit(1)
        )
        if dataset and dataset.lower().startswith(_MATHS_DATASET_PREFIXES):
            subject = cache.get("mathematics")
            if subject is None:
                subject = ensure_subject(db, "mathematics")
                cache["mathematics"] = subject
            topic.source = dataset
        else:
            subject = cache.get("computer-science")
            if subject is None:
                subject = ensure_subject(db, "computer-science")
                cache["computer-science"] = subject
            # The only unlabelled topics this app ever had were the original
            # Computer Science demo (deleted). Mark them explicitly so they are
            # not mistaken for curated or imported content.
            if topic.source in (None, "", "curated"):
                topic.source = "legacy"
        topic.subject_id = subject.id
        updated += 1

    if updated:
        db.flush()
    return updated
