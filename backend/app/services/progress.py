from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import QuizAttempt, StudyRecord, Topic
from .mastery import as_utc, latest_mastery


def topic_mastery_rows(db: Session, student_id: int) -> list[dict]:
    """Mastery and activity for every topic, including untouched topics."""
    topics = db.scalars(select(Topic).order_by(Topic.name)).all()
    rows: list[dict] = []

    for topic in topics:
        mastery = latest_mastery(db, student_id, topic.id)
        attempts = db.scalar(
            select(func.count(QuizAttempt.id)).where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.topic_id == topic.id,
            )
        )
        last_attempt = db.scalar(
            select(func.max(QuizAttempt.attempted_at)).where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.topic_id == topic.id,
            )
        )
        rows.append(
            {
                "topic_id": topic.id,
                "topic_name": topic.name,
                "difficulty": topic.difficulty,
                "mastery": mastery if mastery is not None else settings.bkt_prior,
                "attempts": int(attempts or 0),
                "last_attempt_at": as_utc(last_attempt),
            }
        )
    return rows


def study_totals(db: Session, student_id: int) -> tuple[int, int]:
    minutes = db.scalar(
        select(func.coalesce(func.sum(StudyRecord.duration_minutes), 0)).where(
            StudyRecord.student_id == student_id
        )
    )
    attempts = db.scalar(
        select(func.count(QuizAttempt.id)).where(QuizAttempt.student_id == student_id)
    )
    return int(minutes or 0), int(attempts or 0)
