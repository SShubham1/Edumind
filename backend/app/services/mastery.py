from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import MasterySnapshot, QuizAttempt


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; normalise before doing arithmetic."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def bkt_update(mastery: float, correct: bool) -> float:
    """One Bayesian Knowledge Tracing update step.

    Defaults live in config; a later model-fitting job can replace them with
    per-topic parameters without changing the API.
    """
    prior = clamp(mastery)
    guess = clamp(settings.bkt_guess)
    slip = clamp(settings.bkt_slip)
    learn = clamp(settings.bkt_learn)

    if correct:
        numerator = prior * (1.0 - slip)
        denominator = numerator + (1.0 - prior) * guess
    else:
        numerator = prior * slip
        denominator = numerator + (1.0 - prior) * (1.0 - guess)

    posterior = numerator / denominator if denominator > 0 else prior
    return clamp(posterior + (1.0 - posterior) * learn)


def latest_mastery(db: Session, student_id: int, topic_id: int) -> float | None:
    row = db.scalars(
        select(MasterySnapshot)
        .where(
            MasterySnapshot.student_id == student_id,
            MasterySnapshot.topic_id == topic_id,
        )
        .order_by(MasterySnapshot.created_at.desc(), MasterySnapshot.id.desc())
        .limit(1)
    ).first()
    return row.mastery if row else None


def apply_quiz_attempt(
    db: Session,
    student_id: int,
    topic_id: int,
    correct_answers: int,
    total_questions: int,
    attempted_at: datetime | None = None,
    snapshot_at: datetime | None = None,
) -> tuple[QuizAttempt, float]:
    """Store an attempt and add a mastery snapshot.

    The caller is responsible for committing the transaction. `snapshot_at`
    lets ETL imports timestamp historical snapshots at the original attempt
    time so mastery history keeps its chronological order.
    """
    score = correct_answers / total_questions
    attempt = QuizAttempt(
        student_id=student_id,
        topic_id=topic_id,
        correct_answers=correct_answers,
        total_questions=total_questions,
        score=score,
        attempted_at=attempted_at or datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.flush()

    baseline = latest_mastery(db, student_id, topic_id)
    if baseline is None:
        baseline = settings.bkt_prior

    # Aggregate update for the whole attempt: blend the "all correct" and
    # "all wrong" BKT posteriors by the observed score.
    after_correct = bkt_update(baseline, True)
    after_wrong = bkt_update(baseline, False)
    new_mastery = clamp(score * after_correct + (1.0 - score) * after_wrong)

    db.add(
        MasterySnapshot(
            student_id=student_id,
            topic_id=topic_id,
            mastery=new_mastery,
            source="quiz",
            created_at=snapshot_at or datetime.now(timezone.utc),
        )
    )
    db.flush()
    return attempt, new_mastery
