from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Subject, Topic
from ..schemas import TopicCreate, TopicOut
from ..subjects import resolve_or_register_subject, resolve_subject

router = APIRouter(prefix="/api/topics", tags=["topics"])


def _resolve(db: Session, subject: str | int) -> Subject:
    try:
        return resolve_subject(db, subject)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _resolve_or_create(db: Session, subject: str | int) -> Subject:
    try:
        return resolve_or_register_subject(db, subject)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("", response_model=list[TopicOut])
def list_topics(
    subject: str | None = Query(
        default=None,
        description="Filter by subject key, name or id (e.g. `mathematics`).",
    ),
    db: Session = Depends(get_db),
):
    query = select(Topic).order_by(Topic.name)
    if subject is not None:
        query = query.where(Topic.subject_id == _resolve(db, subject).id)
    return db.scalars(query).all()


@router.post("", response_model=TopicOut, status_code=201)
def create_topic(payload: TopicCreate, db: Session = Depends(get_db)):
    # Known registry keys (e.g. "trading") create their subject on first
    # content; arbitrary unknown subjects are rejected.
    subject = _resolve_or_create(db, payload.subject)
    values = payload.model_dump(exclude={"subject"})
    topic = Topic(**values, subject_id=subject.id, source="curated")
    db.add(topic)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "A topic with this name already exists. Topic names are unique "
                "across subjects, so prefix the name with the subject if needed."
            ),
        )
    db.refresh(topic)
    return topic
