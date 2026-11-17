from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MasterySnapshot, RecommendationLog, Student, Subject, Topic
from ..schemas import (
    MasteryHistoryPoint,
    MasteryOut,
    ProgressOut,
    RecommendationOut,
    StudentCreate,
    StudentOut,
    StudyPlanOut,
)
from ..services.llm import generate_study_plan
from ..services.progress import study_totals, topic_mastery_rows
from ..services.recommendations import compute_recommendations
from ..subjects import resolve_subject

router = APIRouter(prefix="/api/students", tags=["students"])


def _student_or_404(db: Session, student_id: int) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    return student


def _subject_or_404(db: Session, subject: str | int) -> Subject:
    try:
        return resolve_subject(db, subject)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("", response_model=list[StudentOut])
def list_students(
    q: str | None = Query(
        default=None,
        max_length=120,
        description="Case-insensitive search over name and email.",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=5000,
        description="Maximum students to return. Omit for all students.",
    ),
    db: Session = Depends(get_db),
):
    """List students, optionally searched and limited.

    The ASSISTments import creates thousands of students, so the dashboard
    should pass ``q`` and/or ``limit`` instead of loading every row.
    """
    query = select(Student).order_by(Student.name)
    if q:
        needle = f"%{q.strip().casefold()}%"
        query = query.where(
            or_(
                func.lower(Student.name).like(needle),
                func.lower(Student.email).like(needle),
            )
        )
    if limit is not None:
        query = query.limit(limit)
    return db.scalars(query).all()


@router.post("", response_model=StudentOut, status_code=201)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    student = Student(**payload.model_dump())
    db.add(student)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A student with this email already exists.")
    db.refresh(student)
    return student


@router.get("/{student_id}", response_model=StudentOut)
def get_student(student_id: int, db: Session = Depends(get_db)):
    return _student_or_404(db, student_id)


@router.get("/{student_id}/mastery", response_model=list[MasteryOut])
def get_mastery(
    student_id: int,
    subject: str | None = Query(default=None, description="Subject key, name or id."),
    db: Session = Depends(get_db),
):
    _student_or_404(db, student_id)
    subject_id = _subject_or_404(db, subject).id if subject is not None else None
    return topic_mastery_rows(db, student_id, subject_id=subject_id)


@router.get("/{student_id}/progress", response_model=ProgressOut)
def get_progress(
    student_id: int,
    subject: str | None = Query(default=None, description="Subject key, name or id."),
    db: Session = Depends(get_db),
):
    student = _student_or_404(db, student_id)
    subject_id = _subject_or_404(db, subject).id if subject is not None else None
    topics = topic_mastery_rows(db, student_id, subject_id=subject_id)
    minutes, attempts = study_totals(db, student_id, subject_id=subject_id)
    overall = sum(row["mastery"] for row in topics) / len(topics) if topics else 0.0
    return ProgressOut(
        student=student,
        subject_id=subject_id,
        overall_mastery=round(overall, 4),
        total_study_minutes=minutes,
        total_attempts=attempts,
        topics=[MasteryOut(**row) for row in topics],
    )


@router.get("/{student_id}/mastery-history", response_model=list[MasteryHistoryPoint])
def get_mastery_history(
    student_id: int,
    topic_id: int | None = Query(default=None, ge=1),
    subject: str | None = Query(default=None, description="Subject key, name or id."),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    _student_or_404(db, student_id)
    query = select(MasterySnapshot).where(MasterySnapshot.student_id == student_id)
    if topic_id is not None:
        query = query.where(MasterySnapshot.topic_id == topic_id)
    if subject is not None:
        subject_id = _subject_or_404(db, subject).id
        query = query.join(Topic, Topic.id == MasterySnapshot.topic_id).where(
            Topic.subject_id == subject_id
        )
    rows = db.scalars(
        query.order_by(MasterySnapshot.created_at.asc(), MasterySnapshot.id.asc()).limit(limit)
    ).all()
    return rows


@router.get("/{student_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations(
    student_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    subject: str | None = Query(default=None, description="Subject key, name or id."),
    db: Session = Depends(get_db),
):
    _student_or_404(db, student_id)
    subject_id = _subject_or_404(db, subject).id if subject is not None else None
    recommendations = compute_recommendations(
        db, student_id, limit=limit, subject_id=subject_id
    )
    db.add_all(
        [
            RecommendationLog(
                student_id=student_id,
                topic_id=item["topic_id"],
                score=item["score"],
                reason=item["reason"],
            )
            for item in recommendations
        ]
    )
    db.commit()
    return recommendations


@router.post("/{student_id}/study-plan", response_model=StudyPlanOut)
async def create_study_plan(
    student_id: int,
    subject: str | None = Query(default=None, description="Subject key, name or id."),
    db: Session = Depends(get_db),
):
    student = _student_or_404(db, student_id)
    subject_id = _subject_or_404(db, subject).id if subject is not None else None
    recommendations = compute_recommendations(
        db, student_id, limit=4, subject_id=subject_id
    )
    return await generate_study_plan(student.name, recommendations)
