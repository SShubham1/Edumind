from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subject(Base):
    """A curriculum domain such as Mathematics or Computer Science.

    Topics belong to a subject so that mastery, recommendations and charts can
    be scoped: a student's maths and cooking topics should not be ranked in the
    same list.
    """

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable so rows created before the subject model existed can be
    # backfilled by ``app.subjects.ensure_subjects``.
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id"), index=True, nullable=True
    )
    # Provenance: seed | curated | assistments-2009-10 | plugin:<slug>
    source: Mapped[str] = mapped_column(String(60), default="curated")
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Difficulty in [0, 1]; higher means harder.
    difficulty: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudyRecord(Base):
    __tablename__ = "study_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    studied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    correct_answers: Mapped[int] = mapped_column(Integer)
    total_questions: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MasterySnapshot(Base):
    __tablename__ = "mastery_history"
    __table_args__ = (
        Index("ix_mastery_student_topic_created", "student_id", "topic_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    mastery: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40), default="quiz")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecommendationLog(Base):
    __tablename__ = "recommendation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(80))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Flashcard(Base):
    __tablename__ = "flashcards"
    __table_args__ = (
        Index("ix_flashcards_student_topic_created", "student_id", "topic_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    # llm | fallback | manual | seed
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProblemResponse(Base):
    """One validated problem response from an external dataset.

    Raw responses are kept for auditability and for rebuilding mastery or
    evaluating models. `quiz_attempt_id` links a response to the aggregated
    attempt created by the ETL attempt builder.
    """

    __tablename__ = "problem_responses"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_row_hash", name="uq_problem_responses_source_hash"
        ),
        Index(
            "ix_problem_responses_student_topic_time",
            "student_id",
            "topic_id",
            "responded_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    quiz_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("quiz_attempts.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(80), index=True)
    source_row_hash: Mapped[str] = mapped_column(String(64))
    external_user_id: Mapped[str] = mapped_column(String(80))
    external_skill_id: Mapped[str | None] = mapped_column(String(80))
    skill_name: Mapped[str | None] = mapped_column(String(160))
    assignment_id: Mapped[str | None] = mapped_column(String(80))
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hint_count: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int | None] = mapped_column(Integer)
    response_ms: Mapped[int | None] = mapped_column(Integer)
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
