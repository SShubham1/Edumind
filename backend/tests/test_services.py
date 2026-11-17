from datetime import datetime, timedelta, timezone

from app.models import Student, Topic
from app.services.llm import _parse_flashcards, _parse_quiz
from app.services.mastery import apply_quiz_attempt, bkt_update
from app.services.recommendations import compute_recommendations


def test_bkt_update_moves_mastery_in_expected_direction():
    baseline = 0.30
    assert bkt_update(baseline, True) > baseline
    assert bkt_update(baseline, False) < baseline


def test_quiz_attempts_create_history_and_rankings(db):
    student = Student(name="Test Student", email="test@example.com")
    weak_topic = Topic(name="Binary Trees", difficulty=0.6)
    strong_topic = Topic(name="Arrays", difficulty=0.2)
    db.add_all([student, weak_topic, strong_topic])
    db.commit()

    first, mastery_after_weak = apply_quiz_attempt(
        db, student.id, weak_topic.id, correct_answers=2, total_questions=10
    )
    second, mastery_after_strong = apply_quiz_attempt(
        db,
        student.id,
        strong_topic.id,
        correct_answers=9,
        total_questions=10,
        attempted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.commit()

    assert first.score == 0.2
    assert second.score == 0.9
    assert mastery_after_strong > mastery_after_weak

    recommendations = compute_recommendations(db, student.id, limit=2)
    assert len(recommendations) == 2
    assert recommendations[0]["score"] >= recommendations[1]["score"]
    assert recommendations[0]["reason"]
    assert set(recommendations[0]["contributions"]) == {
        "low_mastery",
        "revision",
        "difficulty",
        "recent_weakness",
    }


def test_flashcard_json_parsing_validates_and_limits():
    fenced = """```json
    [
      {"question": "Q1", "answer": "A1"},
      {"question": "Q2", "answer": "A2"},
      {"question": "", "answer": "skip me"},
      {"question": "Q3", "answer": "A3"},
      {"question": "Q4", "answer": "A4"}
    ]
    ```"""
    cards = _parse_flashcards(fenced, count=2)
    assert cards == [
        {"question": "Q1", "answer": "A1"},
        {"question": "Q2", "answer": "A2"},
    ]

    wrapped = '{"flashcards": [{"question": "Q", "answer": "A"}]}'
    assert _parse_flashcards(wrapped, count=5) == [{"question": "Q", "answer": "A"}]

    assert _parse_flashcards("not json at all", count=5) == []
    assert _parse_flashcards("[]", count=5) == []


def test_quiz_json_parsing_validates_questions():
    topic_names = {1: "Fractions", 2: "Patterns"}
    fenced = """```json
    [
      {"topic_id": 1, "question": "Q1", "options": ["a", "b", "c", "d"], "correct_index": 2, "explanation": "E1"},
      {"topic_id": 99, "question": "unknown topic", "options": ["a", "b", "c", "d"], "correct_index": 0, "explanation": "E"},
      {"topic_id": 1, "question": "three options", "options": ["a", "b", "c"], "correct_index": 0, "explanation": "E"},
      {"topic_id": 1, "question": "duplicate options", "options": ["a", "a", "c", "d"], "correct_index": 0, "explanation": "E"},
      {"topic_id": 1, "question": "bad index", "options": ["a", "b", "c", "d"], "correct_index": 4, "explanation": "E"},
      {"topic_id": 2, "question": "Q2", "options": ["w", "x", "y", "z"], "correct_index": 1, "explanation": "E2"}
    ]
    ```"""
    questions = _parse_quiz(fenced, topic_names, count=5)
    assert [item["question"] for item in questions] == ["Q1", "Q2"]
    assert questions[0]["topic_name"] == "Fractions"
    assert questions[0]["correct_index"] == 2
    assert questions[1]["correct_index"] == 1

    # Duplicate question text is discarded case-insensitively.
    duplicate = (
        '[{"topic_id": 1, "question": "Q1", "options": ["a", "b", "c", "d"], '
        '"correct_index": 0, "explanation": "E"}, '
        '{"topic_id": 1, "question": "q1", "options": ["a", "b", "c", "d"], '
        '"correct_index": 0, "explanation": "E"}]'
    )
    assert len(_parse_quiz(duplicate, topic_names, count=5)) == 1

    wrapped = (
        '{"questions": [{"topic_id": 2, "question": "Q", "options": '
        '["a", "b", "c", "d"], "correct_index": 0, "explanation": "E"}]}'
    )
    assert len(_parse_quiz(wrapped, topic_names, count=5)) == 1

    # A short lead-in before the payload is tolerated; trailing prose is ignored.
    prose = (
        'Here is the quiz:\n[{"topic_id": 1, "question": "Q", "options": '
        '["a", "b", "c", "d"], "correct_index": 0, "explanation": "E"}]\nGood luck!'
    )
    assert len(_parse_quiz(prose, topic_names, count=5)) == 1

    assert _parse_quiz("not json", topic_names, count=5) == []
    assert _parse_quiz("[]", topic_names, count=5) == []
