import json
import logging
import re
from datetime import datetime, timezone

import httpx

from ..config import settings
from ..schemas import StudyPlanOut

logger = logging.getLogger(__name__)


def _fallback_plan(student_name: str, recommendations: list[dict]) -> str:
    if not recommendations:
        return (
            f"{student_name}, start by logging a short study session and a diagnostic quiz "
            "for one topic. Once results are recorded, EduMind can rank your study priorities."
        )

    lines = [f"{student_name}, here is a focused plan for the next few days:"]
    for index, rec in enumerate(recommendations[:3], start=1):
        lines.append(
            f"{index}. {rec['topic_name']} (priority {rec['score']:.2f}): {rec['reason']}. "
            "Study for 25 minutes, then attempt 5 practice questions and review mistakes."
        )
    lines.append(
        "Finish with a short mixed quiz and log it, so your mastery estimates and "
        "recommendations update."
    )
    return "\n".join(lines)


def _prompt(student_name: str, recommendations: list[dict]) -> str:
    priorities = "\n".join(
        f"- {rec['topic_name']}: priority {rec['score']:.2f}, mastery "
        f"{rec['mastery']:.2f}, reason: {rec['reason']}"
        for rec in recommendations
    )
    return (
        f"Student: {student_name}\n"
        "Create a concise 3-day study plan using only these ranked topics. "
        "For each day give 2-3 concrete actions (duration and practice type). "
        "Explain briefly why each topic is prioritised. Do not invent topics.\n\n"
        f"Ranked topics:\n{priorities}"
    )


async def generate_study_plan(student_name: str, recommendations: list[dict]) -> StudyPlanOut:
    """Generate a study plan server-side, falling back safely if no key is set."""
    now = datetime.now(timezone.utc)
    fallback = _fallback_plan(student_name, recommendations)

    if not settings.llm_api_key:
        return StudyPlanOut(plan=fallback, source="fallback", generated_at=now)

    payload = {
        "model": settings.llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an academic study coach. Be concise, practical and encouraging. "
                    "Use plain text with short numbered lines."
                ),
            },
            {"role": "user", "content": _prompt(student_name, recommendations)},
        ],
        "temperature": 0.4,
        "max_tokens": 350,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            if content:
                return StudyPlanOut(plan=content, source="llm", generated_at=now)
    except Exception as exc:  # noqa: BLE001 - fallback is intentional
        # Never log request headers or the API key.
        logger.warning("LLM study-plan request failed, using fallback: %s", type(exc).__name__)

    return StudyPlanOut(plan=fallback, source="fallback", generated_at=now)


def _fallback_flashcards(topic_name: str, count: int) -> list[dict]:
    """Deterministic study cards that do not invent topic facts.

    They prompt retrieval practice and self-explanation, so they are still
    useful when no LLM key is configured.
    """
    templates = [
        (
            f"Explain {topic_name} in your own words in under two minutes.",
            "Write a short definition, one worked example and one common mistake.",
        ),
        (
            f"What is the first step you take when solving a {topic_name} problem?",
            "State the step, then solve one problem while narrating it aloud.",
        ),
        (
            f"Which part of {topic_name} did you get wrong most recently?",
            "Review the last quiz mistake and write the corrected reasoning.",
        ),
        (
            f"Give one real-world example that uses {topic_name}.",
            "Describe the example in two sentences and note the key assumption.",
        ),
        (
            f"What is a common mistake students make in {topic_name}?",
            "Name the mistake and explain how to avoid it.",
        ),
        (
            f"Solve one {topic_name} problem without looking at your notes.",
            "Then check the solution and list any step you missed.",
        ),
        (
            f"How does {topic_name} connect to another topic you have studied?",
            "State the connection and one shared principle.",
        ),
        (
            f"What is the key formula or rule in {topic_name}?",
            "Write it from memory, then explain when it applies.",
        ),
        (
            f"Teach {topic_name} to a friend in three sentences.",
            "Use plain language and avoid jargon.",
        ),
        (
            f"What will you practise next in {topic_name}?",
            "Choose a 10-minute exercise and log the attempt.",
        ),
    ]
    return [
        {"question": question, "answer": answer}
        for question, answer in templates[: max(1, min(count, len(templates)))]
    ]


def _flashcard_prompt(
    student_name: str,
    topic_name: str,
    difficulty: float,
    mastery: float,
    count: int,
) -> str:
    return (
        f"Student: {student_name}\n"
        f"Topic: {topic_name} (difficulty {difficulty:.2f}, current mastery {mastery:.0%})\n"
        f"Write {count} study flashcards that test active recall of this topic.\n"
        'Return ONLY a JSON array of objects with "question" and "answer" string fields. '
        "Do not use markdown fences or extra commentary. Keep each answer under 60 words. "
        "Use only well-established facts about the topic and do not invent citations."
    )


def _parse_flashcards(content: str, count: int) -> list[dict]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = data.get("flashcards", [])
    if not isinstance(data, list):
        return []

    cards: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if not question or not answer:
            continue
        cards.append({"question": question[:2000], "answer": answer[:4000]})
        if len(cards) >= count:
            break
    return cards


async def generate_flashcards(
    student_name: str,
    topic_name: str,
    difficulty: float,
    mastery: float,
    count: int = 5,
) -> tuple[list[dict], str]:
    """Generate flashcard drafts server-side, with a deterministic fallback.

    Returns the cards and the source label (``llm`` or ``fallback``). The caller
    persists them; generated content is never trusted without validation.
    """
    fallback = _fallback_flashcards(topic_name, count)

    if not settings.llm_api_key:
        return fallback, "fallback"

    payload = {
        "model": settings.llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You create concise study flashcards for university students. "
                    "Respond with valid JSON only."
                ),
            },
            {
                "role": "user",
                "content": _flashcard_prompt(student_name, topic_name, difficulty, mastery, count),
            },
        ],
        "temperature": 0.5,
        "max_tokens": 900,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        cards = _parse_flashcards(content, count)
        if cards:
            return cards, "llm"
        logger.warning("LLM flashcard response was not usable JSON, using fallback")
    except Exception as exc:  # noqa: BLE001 - fallback is intentional
        # Never log request headers or the API key.
        logger.warning("LLM flashcard request failed, using fallback: %s", type(exc).__name__)

    return fallback, "fallback"
