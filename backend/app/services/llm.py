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


def _quiz_prompt(
    student_name: str,
    focus: list[dict],
    count: int,
) -> str:
    weak = [item for item in focus if item["role"] == "weak"]
    strong = [item for item in focus if item["role"] == "strength"]

    def describe(items: list[dict]) -> str:
        return "\n".join(
            f"- topic_id {item['topic_id']}: {item['topic_name']} "
            f"(mastery {item['mastery']:.0%}; {item['reason']})"
            for item in items
        )

    sections = [
        f"Student: {student_name}",
        "Weak topics — spend most questions here:",
        describe(weak) if weak else "- none recorded",
    ]
    if strong:
        sections.extend(
            [
                "Relative strength — include at most one confidence question:",
                describe(strong),
            ]
        )
    sections.append(
        f"Write {count} multiple-choice questions matched to this profile. "
        "Use only the listed topic_ids. Keep weak-topic questions foundational "
        "and the strength question slightly harder. Four distinct options per "
        "question, exactly one correct, and a short explanation of the reasoning.\n"
        "Use only well-established facts about the topic. Do not invent citations, "
        "statistics or source names. Do not mention that the topic is weak in the "
        "question text.\n"
        'Return ONLY a JSON array of objects with the keys: "topic_id" (integer), '
        '"question" (string), "options" (array of four strings), '
        '"correct_index" (integer 0-3), "explanation" (string). '
        "Do not use markdown fences or extra commentary."
    )
    return "\n\n".join(sections)


def _decode_json(text: str):
    """Decode the first JSON value, tolerating fences and surrounding prose."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Some models emit a sentence or two before the payload. Decode the first
    # complete JSON value and ignore the rest instead of rejecting everything.
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
            return value
        except json.JSONDecodeError:
            continue
    return None


def _parse_quiz(
    content: str,
    topic_names: dict[int, str],
    count: int,
) -> list[dict]:
    """Validate model output and keep only well-formed questions.

    Unknown topics, duplicate or missing options, out-of-range answers and
    duplicate question text are discarded rather than shown to the student.
    Truncated output simply yields no questions, so the caller can retry.
    """
    data = _decode_json(content)
    if data is None:
        return []

    if isinstance(data, dict):
        data = data.get("questions", [])
    if not isinstance(data, list):
        return []

    questions: list[dict] = []
    seen_questions: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            topic_id = int(item.get("topic_id"))
            correct_index = int(item.get("correct_index"))
        except (TypeError, ValueError):
            continue
        if topic_id not in topic_names or not 0 <= correct_index <= 3:
            continue

        question = str(item.get("question", "")).strip()
        explanation = str(item.get("explanation", "")).strip()
        raw_options = item.get("options")
        if not question or not explanation or not isinstance(raw_options, list):
            continue
        if len(raw_options) != 4:
            continue
        options = [str(option).strip() for option in raw_options]
        if any(not option for option in options):
            continue
        if len({option.casefold() for option in options}) != 4:
            continue
        question_key = question.casefold()
        if question_key in seen_questions:
            continue
        seen_questions.add(question_key)

        questions.append(
            {
                "topic_id": topic_id,
                "topic_name": topic_names[topic_id],
                "question": question[:2000],
                "options": [option[:500] for option in options],
                "correct_index": correct_index,
                "explanation": explanation[:2000],
            }
        )
        if len(questions) >= count:
            break
    return questions


async def generate_quiz(
    student_name: str,
    focus: list[dict],
    count: int = 5,
) -> tuple[list[dict], str]:
    """Generate a quiz from the student's weak topics and relative strength.

    Returns ``(questions, "llm")`` on success. If no key is configured or the
    model returns unusable content, returns ``([], "unavailable")`` — EduMind
    does not fabricate quiz questions offline.
    """
    if not settings.llm_api_key:
        return [], "unavailable"

    topic_names = {item["topic_id"]: item["topic_name"] for item in focus}
    payload = {
        "model": settings.llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write short formative quizzes for a study app. "
                    "Output only the JSON array: no reasoning, commentary or "
                    "markdown fences."
                ),
            },
            {"role": "user", "content": _quiz_prompt(student_name, focus, count)},
        ],
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    # Reasoning-capable models sometimes spend the whole budget thinking. If
    # the first response is truncated, retry once with a larger budget.
    budgets = [settings.llm_quiz_max_tokens]
    if settings.llm_quiz_max_tokens < 8000:
        budgets.append(8000)

    for attempt, max_tokens in enumerate(budgets, start=1):
        try:
            async with httpx.AsyncClient(timeout=settings.llm_quiz_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    json={**payload, "max_tokens": max_tokens},
                    headers=headers,
                )
                response.raise_for_status()
                choice = response.json()["choices"][0]
                content = choice["message"]["content"]

            questions = _parse_quiz(content, topic_names, count)
            if questions:
                return questions, "llm"

            if choice.get("finish_reason") != "length" or attempt == len(budgets):
                break
            logger.warning(
                "LLM quiz output was truncated at %s tokens; retrying", max_tokens
            )
        except Exception as exc:  # noqa: BLE001 - the caller reports unavailable
            # Never log request headers or the API key.
            logger.warning("LLM quiz request failed: %s", type(exc).__name__)
            break

    logger.warning("LLM quiz response was not usable JSON")
    return [], "unavailable"
