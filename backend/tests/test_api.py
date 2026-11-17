import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_end_to_end_learning_flow(client: TestClient):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    student = client.post(
        "/api/students",
        json={"name": "API Student", "email": "api@example.com"},
    )
    assert student.status_code == 201
    student_id = student.json()["id"]

    topic = client.post(
        "/api/topics",
        json={"name": "Graphs", "difficulty": 0.7},
    )
    assert topic.status_code == 201
    topic_id = topic.json()["id"]

    study = client.post(
        "/api/study-records",
        json={"student_id": student_id, "topic_id": topic_id, "duration_minutes": 30},
    )
    assert study.status_code == 201

    quiz = client.post(
        "/api/quiz-results",
        json={
            "student_id": student_id,
            "topic_id": topic_id,
            "correct_answers": 3,
            "total_questions": 10,
        },
    )
    assert quiz.status_code == 201
    assert 0.0 <= quiz.json()["mastery"] <= 1.0

    progress = client.get(f"/api/students/{student_id}/progress")
    assert progress.status_code == 200
    body = progress.json()
    assert body["total_study_minutes"] == 30
    assert body["total_attempts"] == 1
    assert body["topics"][0]["attempts"] == 1

    recommendations = client.get(f"/api/students/{student_id}/recommendations")
    assert recommendations.status_code == 200
    assert len(recommendations.json()) == 1
    assert recommendations.json()[0]["reason"]

    plan = client.post(f"/api/students/{student_id}/study-plan")
    assert plan.status_code == 200
    assert plan.json()["source"] == "fallback"
    assert plan.json()["plan"]


def test_flashcard_generation_and_management(client: TestClient):
    student = client.post(
        "/api/students",
        json={"name": "Card Student", "email": "cards@example.com"},
    ).json()
    topic = client.post(
        "/api/topics",
        json={"name": "Probability", "difficulty": 0.6},
    ).json()

    generated = client.post(
        f"/api/students/{student['id']}/flashcards/generate",
        json={"topic_id": topic["id"], "count": 3},
    )
    assert generated.status_code == 201
    batch = generated.json()
    assert batch["source"] == "fallback"
    assert len(batch["flashcards"]) == 3
    assert all(card["question"] and card["answer"] for card in batch["flashcards"])
    assert all(card["student_id"] == student["id"] for card in batch["flashcards"])

    manual = client.post(
        "/api/flashcards",
        json={
            "student_id": student["id"],
            "topic_id": topic["id"],
            "question": "State Bayes' rule.",
            "answer": "P(A|B) = P(B|A) P(A) / P(B).",
        },
    )
    assert manual.status_code == 201
    assert manual.json()["source"] == "manual"

    listing = client.get(f"/api/students/{student['id']}/flashcards")
    assert listing.status_code == 200
    assert len(listing.json()) == 4

    filtered = client.get(
        f"/api/students/{student['id']}/flashcards?topic_id={topic['id']}"
    )
    assert len(filtered.json()) == 4

    deleted = client.delete(f"/api/flashcards/{batch['flashcards'][0]['id']}")
    assert deleted.status_code == 204
    assert len(client.get(f"/api/students/{student['id']}/flashcards").json()) == 3

    missing_topic = client.post(
        f"/api/students/{student['id']}/flashcards/generate",
        json={"topic_id": 9999, "count": 3},
    )
    assert missing_topic.status_code == 404


def test_subjects_scope_topics_progress_and_recommendations(client: TestClient):
    student = client.post(
        "/api/students",
        json={"name": "Subject Student", "email": "subjects@example.com"},
    ).json()

    cs = client.post(
        "/api/topics",
        json={"name": "Linked Lists", "subject": "computer-science", "difficulty": 0.4},
    ).json()
    trading = client.post(
        "/api/topics",
        json={"name": "Moving Averages", "subject": "trading", "difficulty": 0.6},
    ).json()
    assert cs["subject_id"] != trading["subject_id"]
    assert cs["source"] == "curated"

    for topic, correct in ((cs, 9), (trading, 2)):
        response = client.post(
            "/api/quiz-results",
            json={
                "student_id": student["id"],
                "topic_id": topic["id"],
                "correct_answers": correct,
                "total_questions": 10,
            },
        )
        assert response.status_code == 201

    subjects = {item["key"]: item for item in client.get("/api/subjects").json()}
    assert subjects["computer-science"]["topic_count"] == 1
    assert subjects["trading"]["topic_count"] == 1
    # Nothing has declared Mathematics content in this database, so the
    # subject does not exist yet.
    assert "mathematics" not in subjects

    scoped = client.get("/api/topics?subject=trading")
    assert scoped.status_code == 200
    assert [topic["name"] for topic in scoped.json()] == ["Moving Averages"]

    progress = client.get(
        f"/api/students/{student['id']}/progress?subject=trading"
    ).json()
    assert progress["subject_id"] == trading["subject_id"]
    assert progress["total_attempts"] == 1
    assert [row["topic_name"] for row in progress["topics"]] == ["Moving Averages"]

    recommendations = client.get(
        f"/api/students/{student['id']}/recommendations?subject=trading"
    ).json()
    assert [item["topic_id"] for item in recommendations] == [trading["id"]]

    history = client.get(
        f"/api/students/{student['id']}/mastery-history?subject=trading"
    ).json()
    assert all(point["topic_id"] == trading["id"] for point in history)

    assert client.get("/api/topics?subject=nonexistent").status_code == 404
    assert (
        client.post(
            "/api/topics",
            json={"name": "Unknown Subject Topic", "subject": "nonexistent"},
        ).status_code
        == 404
    )


def test_student_list_supports_search_and_limit(client: TestClient):
    for name, email in (
        ("Alice Zephyr", "alice@example.com"),
        ("Alicia Gomez", "alicia@example.com"),
        ("Bob Stone", "bob@example.com"),
    ):
        assert (
            client.post("/api/students", json={"name": name, "email": email}).status_code
            == 201
        )

    searched = client.get("/api/students?q=ali").json()
    assert {student["name"] for student in searched} == {"Alice Zephyr", "Alicia Gomez"}

    by_email = client.get("/api/students?q=bob@example.com").json()
    assert [student["name"] for student in by_email] == ["Bob Stone"]

    limited = client.get("/api/students?limit=2").json()
    assert len(limited) == 2


def _seed_attempt(
    client: TestClient, student_id: int, topic_id: int, correct: int, total: int = 10
) -> None:
    response = client.post(
        "/api/quiz-results",
        json={
            "student_id": student_id,
            "topic_id": topic_id,
            "correct_answers": correct,
            "total_questions": total,
        },
    )
    assert response.status_code == 201


def test_generated_quiz_targets_weak_topics_plus_one_strength(
    client: TestClient, monkeypatch
):
    import app.routers.quizzes as quizzes

    student = client.post(
        "/api/students",
        json={"name": "Quiz Student", "email": "quiz@example.com"},
    ).json()
    weak = client.post(
        "/api/topics", json={"name": "Fractions", "difficulty": 0.6}
    ).json()
    strong = client.post(
        "/api/topics", json={"name": "Patterns", "difficulty": 0.3}
    ).json()
    _seed_attempt(client, student["id"], weak["id"], correct=1)
    _seed_attempt(client, student["id"], strong["id"], correct=9)

    captured: dict = {}

    async def fake_generate(student_name, focus, count=5):
        captured["student_name"] = student_name
        captured["focus"] = focus
        captured["count"] = count
        question = {
            "topic_id": focus[0]["topic_id"],
            "topic_name": focus[0]["topic_name"],
            "question": "What is 1/2 + 1/4?",
            "options": ["3/4", "2/6", "1/8", "1/6"],
            "correct_index": 0,
            "explanation": "Use a common denominator of four.",
        }
        return [question], "llm"

    monkeypatch.setattr(quizzes, "generate_quiz", fake_generate)

    generated = client.post(
        f"/api/students/{student['id']}/quiz/generate",
        json={"count": 3},
    )
    assert generated.status_code == 200
    body = generated.json()
    assert body["source"] == "llm"
    assert body["questions"][0]["topic_name"] == "Fractions"
    assert body["focus"][0]["role"] == "weak"
    assert any(item["role"] == "strength" for item in body["focus"])

    # The prompt is profile-driven: the weak topic is included and the
    # strength is a separate, relative signal.
    roles = {item["role"] for item in captured["focus"]}
    assert roles == {"weak", "strength"}
    assert all(item["topic_id"] in {weak["id"], strong["id"]} for item in captured["focus"])
    assert captured["student_name"] == "Quiz Student"

    # Graded generated questions go through the same mastery path as a manual
    # quiz, so practice feeds the student model.
    graded = client.post(
        "/api/quiz-results",
        json={
            "student_id": student["id"],
            "topic_id": body["questions"][0]["topic_id"],
            "correct_answers": 1,
            "total_questions": 1,
        },
    )
    assert graded.status_code == 201
    assert 0.0 <= graded.json()["mastery"] <= 1.0


def test_generated_quiz_requires_an_llm_key(client: TestClient):
    student = client.post(
        "/api/students",
        json={"name": "Offline Student", "email": "offline@example.com"},
    ).json()
    topic = client.post(
        "/api/topics", json={"name": "Decimals", "difficulty": 0.5}
    ).json()
    _seed_attempt(client, student["id"], topic["id"], correct=3)

    response = client.post(
        f"/api/students/{student['id']}/quiz/generate",
        json={"count": 5},
    )
    assert response.status_code == 503
    assert "LLM" in response.json()["detail"]

    assert (
        client.post("/api/students/9999/quiz/generate", json={"count": 5}).status_code
        == 404
    )


def test_generated_quiz_requires_topics(client: TestClient):
    student = client.post(
        "/api/students",
        json={"name": "New Student", "email": "new@example.com"},
    ).json()

    response = client.post(
        f"/api/students/{student['id']}/quiz/generate",
        json={"count": 5},
    )
    assert response.status_code == 404
