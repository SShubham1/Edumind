from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import QuizAttempt, Topic
from .mastery import as_utc, clamp, latest_mastery


def _reason(
    mastery: float,
    days_since: float | None,
    recent_accuracy: float | None,
    contributions: dict[str, float],
) -> str:
    top = max(contributions, key=contributions.get)
    if top == "low_mastery":
        return f"Low mastery ({mastery:.2f})"
    if top == "revision":
        if days_since is None:
            return "Not practised yet"
        return f"Not revised for {int(days_since)} days"
    if top == "difficulty":
        return "High topic difficulty"
    if recent_accuracy is None:
        return "Needs a first diagnostic quiz"
    return f"Recent accuracy {recent_accuracy:.0%} - needs reinforcement"


def compute_recommendations(
    db: Session,
    student_id: int,
    limit: int = 5,
    subject_id: int | None = None,
) -> list[dict]:
    """Rank topics by expected study priority.

    R(t) = w1(1 - mastery) + w2*revision_urgency + w3*difficulty + w4*weakness

    ``subject_id`` restricts ranking to one subject; without it, topics from
    unrelated domains would be compared against each other.
    """
    now = datetime.now(timezone.utc)
    window = max(settings.revision_window_days, 1.0)
    query = select(Topic).order_by(Topic.name)
    if subject_id is not None:
        query = query.where(Topic.subject_id == subject_id)
    topics = db.scalars(query).all()
    ranked: list[dict] = []

    for topic in topics:
        mastery = latest_mastery(db, student_id, topic.id)
        if mastery is None:
            mastery = settings.bkt_prior

        recent_attempts = db.scalars(
            select(QuizAttempt)
            .where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.topic_id == topic.id,
            )
            .order_by(QuizAttempt.attempted_at.desc(), QuizAttempt.id.desc())
            .limit(3)
        ).all()

        last_attempt = as_utc(recent_attempts[0].attempted_at) if recent_attempts else None
        days_since = (now - last_attempt).total_seconds() / 86400 if last_attempt else None

        if recent_attempts:
            recent_accuracy = sum(a.score for a in recent_attempts) / len(recent_attempts)
        else:
            recent_accuracy = None

        revision = clamp(days_since / window) if days_since is not None else 1.0
        weakness = 1.0 - recent_accuracy if recent_accuracy is not None else 0.6

        contributions = {
            "low_mastery": settings.rec_weight_mastery * (1.0 - mastery),
            "revision": settings.rec_weight_revision * revision,
            "difficulty": settings.rec_weight_difficulty * clamp(topic.difficulty),
            "recent_weakness": settings.rec_weight_weakness * clamp(weakness),
        }
        score = sum(contributions.values())

        ranked.append(
            {
                "topic_id": topic.id,
                "topic_name": topic.name,
                "subject_id": topic.subject_id,
                "score": round(score, 4),
                "mastery": round(mastery, 4),
                "reason": _reason(mastery, days_since, recent_accuracy, contributions),
                "contributions": {key: round(value, 4) for key, value in contributions.items()},
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]
