from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import QuizAttempt, Student, StudyRecord, Topic
from ..schemas import (
    QuizAttemptOut,
    QuizResultCreate,
    QuizResultOut,
    StudyRecordCreate,
    StudyRecordOut,
)
from ..services.mastery import apply_quiz_attempt

router = APIRouter(prefix="/api", tags=["records"])


def _require_student(db: Session, student_id: int) -> None:
    if db.get(Student, student_id) is None:
        raise HTTPException(status_code=404, detail="Student not found.")


def _require_topic(db: Session, topic_id: int) -> None:
    if db.get(Topic, topic_id) is None:
        raise HTTPException(status_code=404, detail="Topic not found.")


@router.post("/study-records", response_model=StudyRecordOut, status_code=201)
def create_study_record(payload: StudyRecordCreate, db: Session = Depends(get_db)):
    _require_student(db, payload.student_id)
    _require_topic(db, payload.topic_id)
    record = StudyRecord(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/students/{student_id}/study-records", response_model=list[StudyRecordOut])
def list_study_records(
    student_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _require_student(db, student_id)
    return db.scalars(
        select(StudyRecord)
        .where(StudyRecord.student_id == student_id)
        .order_by(StudyRecord.studied_at.desc(), StudyRecord.id.desc())
        .limit(limit)
    ).all()


@router.post("/quiz-results", response_model=QuizResultOut, status_code=201)
def submit_quiz_result(payload: QuizResultCreate, db: Session = Depends(get_db)):
    _require_student(db, payload.student_id)
    _require_topic(db, payload.topic_id)
    attempt, mastery = apply_quiz_attempt(
        db,
        student_id=payload.student_id,
        topic_id=payload.topic_id,
        correct_answers=payload.correct_answers,
        total_questions=payload.total_questions,
        attempted_at=payload.attempted_at,
    )
    db.commit()
    db.refresh(attempt)
    return QuizResultOut(attempt=attempt, mastery=mastery)


@router.get("/students/{student_id}/quiz-results", response_model=list[QuizAttemptOut])
def list_quiz_results(
    student_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _require_student(db, student_id)
    return db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.student_id == student_id)
        .order_by(QuizAttempt.attempted_at.desc(), QuizAttempt.id.desc())
        .limit(limit)
    ).all()
