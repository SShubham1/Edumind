from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Flashcard, Student, StudyRecord, Topic
from .services.mastery import apply_quiz_attempt


def seed_demo_data(db: Session) -> bool:
    """Create a small demo dataset once, for local development."""
    if db.scalar(select(func.count(Student.id))):
        return False

    topic_specs = [
        ("Arrays and Lists", "Indexing, traversal and basic array algorithms.", 0.25),
        ("Binary Trees", "Tree traversal, recursion and binary search trees.", 0.55),
        ("Graphs", "Representation, BFS, DFS and shortest paths.", 0.65),
        ("Dynamic Programming", "Memoisation, tabulation and optimisation.", 0.80),
        ("Probability", "Conditional probability, expectation and Bayes' rule.", 0.60),
    ]
    topics = [
        Topic(name=name, description=description, difficulty=difficulty)
        for name, description, difficulty in topic_specs
    ]
    db.add_all(topics)
    db.flush()
    topic_by_name = {topic.name: topic for topic in topics}

    demo = Student(name="Demo Student", email="demo@edumind.local")
    asha = Student(name="Asha Rao", email="asha@edumind.local")
    db.add_all([demo, asha])
    db.flush()

    now = datetime.now(timezone.utc)
    # Oldest first so the mastery history evolves in the right order.
    history = {
        demo.id: [
            ("Dynamic Programming", 2, 8, 16),
            ("Arrays and Lists", 8, 10, 12),
            ("Binary Trees", 3, 10, 8),
            ("Graphs", 5, 10, 4),
        ],
        asha.id: [
            ("Dynamic Programming", 4, 8, 10),
            ("Arrays and Lists", 9, 10, 5),
            ("Probability", 5, 10, 3),
            ("Binary Trees", 6, 10, 2),
            ("Graphs", 7, 10, 1),
        ],
    }
    for student_id, attempts in history.items():
        for topic_name, correct, total, days_ago in sorted(
            attempts, key=lambda item: item[3], reverse=True
        ):
            apply_quiz_attempt(
                db,
                student_id=student_id,
                topic_id=topic_by_name[topic_name].id,
                correct_answers=correct,
                total_questions=total,
                attempted_at=now - timedelta(days=days_ago),
            )

    db.add_all(
        [
            StudyRecord(
                student_id=demo.id,
                topic_id=topic_by_name["Arrays and Lists"].id,
                duration_minutes=40,
                studied_at=now - timedelta(days=13),
                notes="Revised two-pointer problems.",
            ),
            StudyRecord(
                student_id=demo.id,
                topic_id=topic_by_name["Binary Trees"].id,
                duration_minutes=25,
                studied_at=now - timedelta(days=9),
                notes="Tree traversal practice.",
            ),
            StudyRecord(
                student_id=demo.id,
                topic_id=topic_by_name["Graphs"].id,
                duration_minutes=30,
                studied_at=now - timedelta(days=5),
                notes="BFS and DFS exercises.",
            ),
            StudyRecord(
                student_id=asha.id,
                topic_id=topic_by_name["Probability"].id,
                duration_minutes=35,
                studied_at=now - timedelta(days=2),
                notes="Bayes' rule worked examples.",
            ),
        ]
    )

    db.add_all(
        [
            Flashcard(
                student_id=demo.id,
                topic_id=topic_by_name["Dynamic Programming"].id,
                question="What is the difference between memoisation and tabulation?",
                answer=(
                    "Memoisation is top-down recursion with cached results; tabulation is "
                    "bottom-up iteration that fills a table in dependency order."
                ),
                source="seed",
            ),
            Flashcard(
                student_id=demo.id,
                topic_id=topic_by_name["Dynamic Programming"].id,
                question="How do you identify overlapping subproblems?",
                answer=(
                    "Check whether the same smaller inputs are recomputed by different branches "
                    "of the recursion; if so, cache those results."
                ),
                source="seed",
            ),
            Flashcard(
                student_id=demo.id,
                topic_id=topic_by_name["Arrays and Lists"].id,
                question="When is a two-pointer scan preferable to a nested loop?",
                answer=(
                    "When the array is sorted or movement can be monotonic, reducing an "
                    "O(n^2) scan to O(n)."
                ),
                source="seed",
            ),
            Flashcard(
                student_id=asha.id,
                topic_id=topic_by_name["Probability"].id,
                question="State Bayes' rule for two events A and B.",
                answer="P(A|B) = P(B|A) P(A) / P(B), provided P(B) > 0.",
                source="seed",
            ),
            Flashcard(
                student_id=asha.id,
                topic_id=topic_by_name["Graphs"].id,
                question="When does BFS find a shortest path?",
                answer="In an unweighted graph, because it explores vertices in order of edge count.",
                source="seed",
            ),
        ]
    )
    db.commit()
    return True
