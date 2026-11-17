from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.etl.assistments import import_assistments
from app.models import MasterySnapshot, ProblemResponse, QuizAttempt, Topic

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample_assistments.csv"


def test_assistments_etl_imports_valid_rows(db):
    summary = import_assistments(db, SAMPLE_CSV)

    assert summary.rows_read == 17
    assert summary.inserted_responses == 13
    assert summary.duplicate_rows == 1
    assert summary.invalid_rows == 3
    assert summary.students_created == 3
    assert summary.topics_created == 3
    assert summary.attempts_created == 5
    assert summary.mastery_updates == 5

    assert db.scalar(select(func.count(ProblemResponse.id))) == 13
    assert db.scalar(select(func.count(QuizAttempt.id))) == 5
    assert db.scalar(select(func.count(MasterySnapshot.id))) == 5

    unlinked = db.scalar(
        select(func.count(ProblemResponse.id)).where(
            ProblemResponse.quiz_attempt_id.is_(None)
        )
    )
    assert unlinked == 0

    attempts = db.scalars(select(QuizAttempt).order_by(QuizAttempt.id)).all()
    assert [attempt.correct_answers for attempt in attempts] == [2, 1, 2, 1, 2]
    assert [attempt.total_questions for attempt in attempts] == [4, 1, 3, 3, 2]

    snapshots = db.scalars(select(MasterySnapshot)).all()
    assert len(snapshots) == 5
    assert all(0.0 <= snapshot.mastery <= 1.0 for snapshot in snapshots)
    assert all(snapshot.created_at.year == 2026 for snapshot in snapshots)

    linear = db.scalar(select(Topic).where(Topic.name == "Linear Equations"))
    assert linear is not None
    assert abs(linear.difficulty - 0.375) < 1e-6

    skill_55 = db.scalar(select(Topic).where(Topic.name == "Skill 55"))
    assert skill_55 is not None
    assert skill_55.difficulty == 0.05


def test_assistments_etl_is_idempotent(db):
    first = import_assistments(db, SAMPLE_CSV)
    second = import_assistments(db, SAMPLE_CSV)

    assert first.inserted_responses == 13
    assert second.inserted_responses == 0
    assert second.duplicate_rows == 14
    assert second.attempts_created == 0
    assert second.students_created == 0
    assert second.topics_created == 0

    assert db.scalar(select(func.count(ProblemResponse.id))) == 13
    assert db.scalar(select(func.count(QuizAttempt.id))) == 5


def test_assistments_etl_can_limit_skills(db):
    summary = import_assistments(db, SAMPLE_CSV, max_skills=2)

    assert summary.topics_created == 2
    assert summary.inserted_responses == 11
    assert summary.skipped_new_skill_rows == 2


def test_assistments_etl_can_skip_attempt_building(db):
    summary = import_assistments(db, SAMPLE_CSV, build_attempts=False)

    assert summary.inserted_responses == 13
    assert summary.attempts_created == 0
    assert db.scalar(select(func.count(QuizAttempt.id))) == 0
    assert db.scalar(select(func.count(MasterySnapshot.id))) == 0
    assert db.scalar(select(func.count(ProblemResponse.id))) == 13


def test_assistments_etl_reports_missing_columns(db, tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("user_id,skill_id,correct\n1001,21,1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="start_time"):
        import_assistments(db, bad_csv)
