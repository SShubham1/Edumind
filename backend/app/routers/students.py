from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MasterySnapshot, RecommendationLog, Student
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

router = APIRouter(prefix="/api/students", tags=["students"])


def _student_or_404(db: Session, student_id: int) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    return student


@router.get("", response_model=list[StudentOut])
def list_students(db: Session = Depends(get_db)):
    return db.scalars(select(Student).order_by(Student.name)).all()


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
def get_mastery(student_id: int, db: Session = Depends(get_db)):
    _student_or_404(db, student_id)
    return topic_mastery_rows(db, student_id)


@router.get("/{student_id}/progress", response_model=ProgressOut)
def get_progress(student_id: int, db: Session = Depends(get_db)):
    student = _student_or_404(db, student_id)
    topics = topic_mastery_rows(db, student_id)
    minutes, attempts = study_totals(db, student_id)
    overall = sum(row["mastery"] for row in topics) / len(topics) if topics else 0.0
    return ProgressOut(
        student=student,
        overall_mastery=round(overall, 4),
        total_study_minutes=minutes,
        total_attempts=attempts,
        topics=[MasteryOut(**row) for row in topics],
    )


@router.get("/{student_id}/mastery-history", response_model=list[MasteryHistoryPoint])
def get_mastery_history(
    student_id: int,
    topic_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    _student_or_404(db, student_id)
    query = select(MasterySnapshot).where(MasterySnapshot.student_id == student_id)
    if topic_id is not None:
        query = query.where(MasterySnapshot.topic_id == topic_id)
    rows = db.scalars(
        query.order_by(MasterySnapshot.created_at.asc(), MasterySnapshot.id.asc()).limit(limit)
    ).all()
    return rows


@router.get("/{student_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations(
    student_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    _student_or_404(db, student_id)
    recommendations = compute_recommendations(db, student_id, limit=limit)
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
async def create_study_plan(student_id: int, db: Session = Depends(get_db)):
    student = _student_or_404(db, student_id)
    recommendations = compute_recommendations(db, student_id, limit=4)
    return await generate_study_plan(student.name, recommendations)
