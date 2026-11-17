from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import QuizAttempt, StudyRecord, Topic
from .mastery import as_utc, latest_mastery


def topic_mastery_rows(
    db: Session, student_id: int, subject_id: int | None = None
) -> list[dict]:
    """Mastery and activity for topics, including untouched topics.

    When ``subject_id`` is given, only that subject's topics are considered so
    charts and overall mastery do not mix unrelated domains.
    """
    query = select(Topic).order_by(Topic.name)
    if subject_id is not None:
        query = query.where(Topic.subject_id == subject_id)
    topics = db.scalars(query).all()
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
                "subject_id": topic.subject_id,
                "difficulty": topic.difficulty,
                "mastery": mastery if mastery is not None else settings.bkt_prior,
                "attempts": int(attempts or 0),
                "last_attempt_at": as_utc(last_attempt),
            }
        )
    return rows


def study_totals(
    db: Session, student_id: int, subject_id: int | None = None
) -> tuple[int, int]:
    minutes_query = select(
        func.coalesce(func.sum(StudyRecord.duration_minutes), 0)
    ).where(StudyRecord.student_id == student_id)
    attempts_query = select(func.count(QuizAttempt.id)).where(
        QuizAttempt.student_id == student_id
    )
    if subject_id is not None:
        minutes_query = minutes_query.join(
            Topic, Topic.id == StudyRecord.topic_id
        ).where(Topic.subject_id == subject_id)
        attempts_query = attempts_query.join(
            Topic, Topic.id == QuizAttempt.topic_id
        ).where(Topic.subject_id == subject_id)

    minutes = db.scalar(minutes_query)
    attempts = db.scalar(attempts_query)
    return int(minutes or 0), int(attempts or 0)
