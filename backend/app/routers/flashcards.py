from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Flashcard, Student, Topic
from ..schemas import (
    FlashcardBatchOut,
    FlashcardCreate,
    FlashcardGenerateRequest,
    FlashcardOut,
)
from ..services.llm import generate_flashcards
from ..services.mastery import latest_mastery

router = APIRouter(prefix="/api", tags=["flashcards"])


def _student_or_404(db: Session, student_id: int) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    return student


def _topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found.")
    return topic


@router.get("/students/{student_id}/flashcards", response_model=list[FlashcardOut])
def list_flashcards(
    student_id: int,
    topic_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    _student_or_404(db, student_id)
    query = select(Flashcard).where(Flashcard.student_id == student_id)
    if topic_id is not None:
        query = query.where(Flashcard.topic_id == topic_id)
    return db.scalars(
        query.order_by(Flashcard.created_at.desc(), Flashcard.id.desc()).limit(limit)
    ).all()


@router.post("/flashcards", response_model=FlashcardOut, status_code=201)
def create_flashcard(payload: FlashcardCreate, db: Session = Depends(get_db)):
    _student_or_404(db, payload.student_id)
    _topic_or_404(db, payload.topic_id)
    card = Flashcard(
        student_id=payload.student_id,
        topic_id=payload.topic_id,
        question=payload.question.strip(),
        answer=payload.answer.strip(),
        source="manual",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.delete("/flashcards/{flashcard_id}", status_code=204)
def delete_flashcard(flashcard_id: int, db: Session = Depends(get_db)) -> None:
    card = db.get(Flashcard, flashcard_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Flashcard not found.")
    db.delete(card)
    db.commit()


@router.post(
    "/students/{student_id}/flashcards/generate",
    response_model=FlashcardBatchOut,
    status_code=201,
)
async def generate_student_flashcards(
    student_id: int,
    payload: FlashcardGenerateRequest,
    db: Session = Depends(get_db),
):
    """Generate and persist flashcards for one topic.

    Uses the server-side LLM when configured and validated JSON is returned;
    otherwise deterministic retrieval-practice cards are stored instead.
    """
    student = _student_or_404(db, student_id)
    topic = _topic_or_404(db, payload.topic_id)

    mastery = latest_mastery(db, student_id, topic.id)
    if mastery is None:
        mastery = settings.bkt_prior

    drafts, source = await generate_flashcards(
        student_name=student.name,
        topic_name=topic.name,
        difficulty=topic.difficulty,
        mastery=mastery,
        count=payload.count,
    )

    cards = [
        Flashcard(
            student_id=student.id,
            topic_id=topic.id,
            question=draft["question"],
            answer=draft["answer"],
            source=source,
        )
        for draft in drafts
    ]
    db.add_all(cards)
    db.commit()
    for card in cards:
        db.refresh(card)

    return FlashcardBatchOut(flashcards=cards, source=source)
