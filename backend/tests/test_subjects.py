from datetime import datetime, timezone

from sqlalchemy import create_engine, func, inspect, select, text

from app.migrations import ensure_schema
from app.models import ProblemResponse, Student, Topic
from app.services.mastery import apply_quiz_attempt
from app.services.progress import topic_mastery_rows
from app.services.recommendations import compute_recommendations
from app.subjects import backfill_topic_subjects, ensure_subject, resolve_subject


def test_subjects_are_created_by_content_not_upfront(db):

    from app.models import Subject

    # A fresh database has no subjects at all: nothing has declared content.
    assert db.scalar(select(func.count(Subject.id))) == 0

    cs = ensure_subject(db, "computer-science")
    assert ensure_subject(db, "computer-science").id == cs.id
    assert resolve_subject(db, "Computer Science").key == "computer-science"

    maths = ensure_subject(db, "mathematics")
    assert resolve_subject(db, "MATHEMATICS").key == "mathematics"
    assert resolve_subject(db, maths.id).key == "mathematics"


def test_backfill_assigns_imported_topics_to_mathematics(db):
    student = Student(name="Imported", email="imported@example.com")
    maths_topic = Topic(name="Box and Whisker", difficulty=0.5)
    curated_topic = Topic(name="Binary Trees", difficulty=0.5)
    db.add_all([student, maths_topic, curated_topic])
    db.flush()
    db.add(
        ProblemResponse(
            student_id=student.id,
            topic_id=maths_topic.id,
            source="assistments-2009-10",
            source_row_hash="hash-1",
            external_user_id="1001",
            correct=True,
            responded_at=datetime(2010, 1, 4, tzinfo=timezone.utc),
        )
    )
    db.flush()

    updated = backfill_topic_subjects(db)
    assert updated == 2

    db.refresh(maths_topic)
    db.refresh(curated_topic)
    maths = resolve_subject(db, "mathematics")
    cs = resolve_subject(db, "computer-science")
    assert maths_topic.subject_id == maths.id
    assert maths_topic.source == "assistments-2009-10"
    assert curated_topic.subject_id == cs.id
    assert curated_topic.source == "legacy"


def test_mastery_and_recommendations_can_be_scoped_to_a_subject(db):
    cs_subject = ensure_subject(db, "computer-science")
    trading_subject = ensure_subject(db, "trading")
    student = Student(name="Scoped", email="scoped@example.com")
    cs = Topic(name="Arrays", difficulty=0.3, subject_id=cs_subject.id)
    trading = Topic(name="Moving Averages", difficulty=0.7, subject_id=trading_subject.id)
    db.add_all([student, cs, trading])
    db.flush()

    apply_quiz_attempt(db, student.id, cs.id, 9, 10)
    apply_quiz_attempt(db, student.id, trading.id, 2, 10)

    cs_rows = topic_mastery_rows(db, student.id, subject_id=cs_subject.id)
    assert [row["topic_name"] for row in cs_rows] == ["Arrays"]

    all_rows = topic_mastery_rows(db, student.id)
    assert {row["topic_name"] for row in all_rows} == {"Arrays", "Moving Averages"}

    trading_recs = compute_recommendations(
        db, student.id, subject_id=trading_subject.id
    )
    assert [item["topic_name"] for item in trading_recs] == ["Moving Averages"]
    assert trading_recs[0]["subject_id"] == trading_subject.id


def test_ensure_schema_upgrades_a_legacy_topics_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE topics ("
                "id INTEGER PRIMARY KEY, name VARCHAR(160) NOT NULL, "
                "description TEXT, difficulty FLOAT, created_at DATETIME)"
            )
        )
        connection.execute(
            text("INSERT INTO topics (id, name, difficulty) VALUES (1, 'Legacy', 0.5)")
        )

    applied = ensure_schema(engine)
    assert "topics.subject_id" in applied
    assert "topics.source" in applied

    columns = {column["name"] for column in inspect(engine).get_columns("topics")}
    assert {"subject_id", "source"} <= columns

    # Running again is a no-op.
    assert ensure_schema(engine) == []

    with engine.connect() as connection:
        value = connection.execute(text("SELECT source FROM topics")).scalar_one()
        assert value == "curated"

    engine.dispose()
