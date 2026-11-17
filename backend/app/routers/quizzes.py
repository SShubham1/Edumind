from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Student
from ..schemas import (
    QuizFocusOut,
    QuizGenerateOut,
    QuizGenerateRequest,
)
from ..services.llm import generate_quiz
from ..services.progress import topic_mastery_rows
from ..services.recommendations import compute_recommendations
from ..subjects import resolve_subject

router = APIRouter(prefix="/api", tags=["quizzes"])

# Only call a topic a strength once mastery is meaningfully above the BKT prior.
_STRENGTH_THRESHOLD = 0.6


def _focus_topics(
    db: Session,
    student_id: int,
    subject_id: int | None,
) -> list[QuizFocusOut]:
    """Pick weak topics plus one relative strength from the student's history."""
    rows = topic_mastery_rows(db, student_id, subject_id=subject_id)
    if not rows:
        raise HTTPException(status_code=404, detail="No topics available for a quiz.")

    attempted = [row for row in rows if row["attempts"] > 0]
    strength: dict | None = None
    if len(attempted) >= 2:
        candidate = max(attempted, key=lambda row: row["mastery"])
        if candidate["mastery"] >= _STRENGTH_THRESHOLD:
            strength = candidate

    strength_id = strength["topic_id"] if strength else None
    weak: list[QuizFocusOut] = []
    recommendations = compute_recommendations(
        db, student_id, limit=8, subject_id=subject_id
    )
    for item in recommendations:
        if item["topic_id"] == strength_id:
            continue
        weak.append(
            QuizFocusOut(
                topic_id=item["topic_id"],
                topic_name=item["topic_name"],
                mastery=item["mastery"],
                role="weak",
                reason=item["reason"],
            )
        )
        if len(weak) == 3:
            break

    focus = list(weak)
    if strength is not None and weak:
        focus.append(
            QuizFocusOut(
                topic_id=strength["topic_id"],
                topic_name=strength["topic_name"],
                mastery=strength["mastery"],
                role="strength",
                reason="Your strongest attempted topic",
            )
        )

    if not focus:
        raise HTTPException(status_code=404, detail="No topics available for a quiz.")
    return focus


@router.post("/students/{student_id}/quiz/generate", response_model=QuizGenerateOut)
async def generate_student_quiz(
    student_id: int,
    payload: QuizGenerateRequest,
    subject: str | None = Query(default=None, description="Subject key, name or id."),
    db: Session = Depends(get_db),
):
    """Generate multiple-choice questions from weak topics and a strength.

    Questions are not persisted. Submitting the graded result through
    ``POST /api/quiz-results`` updates mastery exactly like a manually logged
    quiz, so generated practice feeds the same model.
    """
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")

    subject_id = None
    if subject is not None:
        try:
            subject_id = resolve_subject(db, subject).id
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    focus = _focus_topics(db, student_id, subject_id)
    questions, source = await generate_quiz(
        student.name,
        [item.model_dump() for item in focus],
        count=payload.count,
    )
    if source != "llm" or not questions:
        raise HTTPException(
            status_code=503,
            detail=(
                "Quiz generation needs a working LLM key. Set LLM_API_KEY in "
                "backend/.env and restart the backend, then try again."
            ),
        )

    return QuizGenerateOut(
        questions=questions,
        focus=focus,
        source="llm",
        generated_at=datetime.now(timezone.utc),
    )
