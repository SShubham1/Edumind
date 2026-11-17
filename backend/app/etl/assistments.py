"""ASSISTments 2009-10 Skill Builder ETL.

Pipeline:
1. Extract rows from the Skill Builder CSV (auto-detects UTF-8 vs Latin-1).
2. Validate external user, skill and correctness fields; timestamps are used
   when present.
3. Transform external IDs into EduMind students, topics and canonical records.
4. Load deduplicated ``problem_responses`` rows.
5. Aggregate responses into daily quiz attempts and update mastery history.

The official 2009-10 file has **no timestamp column** — only ``order_id``
(chronological) and response durations. For such files the importer builds a
deterministic pseudo-timeline: each new assignment for a student advances one
day, and responses inside an assignment advance by their response time. Dates
are therefore synthetic and should not be read as real calendar history.

The importer streams the file in batches, so it can handle the full dataset
without loading the whole CSV into memory.

Typical usage::

    cd backend
    .venv/bin/python -m app.etl.assistments \
        --csv data/skill_builder_data.csv \
        --max-skills 20

Re-running the same file is safe: rows are deduplicated by a stable hash of
dataset, user, skill, assignment, order ID, timestamp and correctness.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..database import Base, SessionLocal, engine
from ..models import ProblemResponse, Student, Topic
from ..services.mastery import apply_quiz_attempt, clamp

logger = logging.getLogger("edumind.etl")

_TRUE_VALUES = {"1", "true", "t", "yes", "y", "correct"}
_FALSE_VALUES = {"0", "false", "f", "no", "n", "incorrect", "wrong"}

_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%Y%m%d",
)

# Header aliases cover the official 2009-10 Skill Builder file and common
# re-exports of it.
_USER_COLUMNS = ("user_id", "userid", "student_id", "studentid", "user")
_SKILL_NAME_COLUMNS = ("skill_name", "skillname", "skill")
_SKILL_ID_COLUMNS = ("skill_id", "skillid")
_CORRECT_COLUMNS = ("correct", "is_correct", "correctanswer", "correct_answer")
_TIME_COLUMNS = ("start_time", "starttime", "first_response_time", "timestamp", "time")
_ASSIGNMENT_COLUMNS = ("assignment_id", "assignmentid", "sequence_id", "sequenceid")
_ORDER_COLUMNS = ("order_id", "orderid", "row_id", "rowid", "problem_log_id")
_HINT_COLUMNS = ("hint_count", "hintcount", "hints")
_ATTEMPT_COLUMNS = ("attempt_count", "attemptcount", "attempts")
_RESPONSE_MS_COLUMNS = ("ms_first_response", "msfirstresponse", "response_time_ms")


@dataclass
class ImportSummary:
    dataset: str
    csv_path: str
    rows_read: int = 0
    inserted_responses: int = 0
    duplicate_rows: int = 0
    invalid_rows: int = 0
    skipped_new_skill_rows: int = 0
    students_created: int = 0
    topics_created: int = 0
    attempts_created: int = 0
    mastery_updates: int = 0
    synthetic_timestamps: int = 0
    invalid_examples: list[str] = field(default_factory=list)


@dataclass
class _AttemptGroup:
    correct: int = 0
    total: int = 0
    last_at: datetime | None = None
    response_ids: list[int] = field(default_factory=list)


# Anchor for files without timestamps. 2010-01-04 is a Monday inside the
# 2009-10 school year, so synthetic history reads plausibly on charts.
_SYNTHETIC_BASE = datetime(2010, 1, 4, 9, 0, tzinfo=timezone.utc)
_SYNTHETIC_DAY = timedelta(days=1)
_MAX_RESPONSE_MS = 10 * 60 * 1000
_MAX_OFFSET_MS = 6 * 60 * 60 * 1000
_FALLBACK_PER_DAY = 20


class _SyntheticClock:
    """Deterministic pseudo-timeline for CSVs without absolute timestamps.

    ``order_id`` in the ASSISTments files is chronological, so rows arrive in
    the order the student worked. Each change of ``assignment_id`` advances the
    clock one day and responses inside an assignment advance by their measured
    response time. This keeps daily attempt grouping meaningful while making
    the timestamp difference between two imports of the same file zero.
    """

    def __init__(self, base: datetime = _SYNTHETIC_BASE) -> None:
        self._base = base
        self._state: dict[str, tuple[str, datetime, int]] = {}
        self._counts: dict[str, int] = {}

    def next_timestamp(
        self,
        user_id: str,
        assignment_id: str,
        response_ms: int | None,
    ) -> datetime:
        duration = response_ms if response_ms and response_ms > 0 else 60_000
        duration = min(duration, _MAX_RESPONSE_MS)

        if not assignment_id:
            # Nothing identifies a sitting: use 20 responses per synthetic day.
            count = self._counts.get(user_id, 0)
            self._counts[user_id] = count + 1
            day = count // _FALLBACK_PER_DAY
            offset = (count % _FALLBACK_PER_DAY) * duration
            timestamp = self._base + timedelta(days=day, milliseconds=offset)
            self._state[user_id] = ("", self._base + timedelta(days=day), offset + duration)
            return timestamp

        state = self._state.get(user_id)
        if state is None:
            start, offset = self._base, 0
        else:
            previous_assignment, previous_start, previous_offset = state
            if previous_assignment and assignment_id != previous_assignment:
                start, offset = previous_start + _SYNTHETIC_DAY, 0
            else:
                start, offset = previous_start, previous_offset

        offset = min(offset, _MAX_OFFSET_MS)
        timestamp = start + timedelta(milliseconds=offset)
        self._state[user_id] = (assignment_id, start, offset + duration)
        return timestamp


def _normalise_header(name: str) -> str:
    cleaned = name.replace("\ufeff", "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _detect_encoding(path: Path, sample_size: int = 1 << 20) -> str:
    """Return a safe text encoding for the CSV.

    The official 2009-10 file contains a few non-UTF-8 bytes (mostly in free-text
    answer fields), sometimes after the first megabyte, so this is only a first
    guess; ``_iter_decoded_lines`` handles stray bytes line by line.
    """
    with path.open("rb") as handle:
        sample = handle.read(sample_size)
    cut = sample.rfind(b"\n")
    if cut != -1:
        sample = sample[:cut]
    try:
        sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "latin-1"
    return "utf-8-sig"


def _iter_decoded_lines(path: Path, encoding: str) -> Iterator[str]:
    """Yield lines decoded with ``encoding``, falling back to Latin-1 per line.

    ASSISTments files are mostly UTF-8 with a handful of Latin-1 bytes in
    free-text fields. Decoding each line separately keeps valid UTF-8 intact
    instead of forced-decoding the whole file or replacing every field.
    """
    with path.open("rb") as handle:
        for line in handle:
            try:
                yield line.decode(encoding)
            except UnicodeDecodeError:
                yield line.decode("latin-1")


def _detect_columns(fieldnames: list[str]) -> dict[str, str | None]:
    normalised = {_normalise_header(name): name for name in fieldnames}

    def find(aliases: tuple[str, ...]) -> str | None:
        for alias in aliases:
            if alias in normalised:
                return normalised[alias]
        return None

    columns = {
        "user": find(_USER_COLUMNS),
        "skill_name": find(_SKILL_NAME_COLUMNS),
        "skill_id": find(_SKILL_ID_COLUMNS),
        "correct": find(_CORRECT_COLUMNS),
        "start_time": find(_TIME_COLUMNS),
        "assignment": find(_ASSIGNMENT_COLUMNS),
        "order": find(_ORDER_COLUMNS),
        "hints": find(_HINT_COLUMNS),
        "attempts": find(_ATTEMPT_COLUMNS),
        "response_ms": find(_RESPONSE_MS_COLUMNS),
    }

    missing = [
        label
        for key, label in (
            ("user", "user_id"),
            ("correct", "correct"),
        )
        if not columns[key]
    ]
    if not columns["skill_name"] and not columns["skill_id"]:
        missing.append("skill_name or skill_id")
    if missing:
        raise ValueError(
            "CSV is missing required column(s): "
            + ", ".join(missing)
            + f". Found headers: {', '.join(fieldnames)}"
        )
    return columns


def _parse_correct(value: str) -> bool | None:
    text = value.strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return None


def _parse_int(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None

    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None and numeric > 0:
        if numeric > 1e12:  # milliseconds
            numeric /= 1000.0
        if numeric > 1e9:  # plausible Unix seconds
            try:
                return datetime.fromtimestamp(numeric, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None

    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError:
        parsed = None

    if parsed is None:
        for fmt in _TIMESTAMP_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_row(
    raw: dict[str, Any],
    columns: dict[str, str | None],
    dataset: str,
) -> dict[str, Any] | None:
    user_id = _clean(raw.get(columns["user"])) if columns["user"] else ""
    if not user_id:
        return None

    correct = _parse_correct(
        _clean(raw.get(columns["correct"])) if columns["correct"] else ""
    )
    if correct is None:
        return None

    responded_at = _parse_timestamp(
        _clean(raw.get(columns["start_time"])) if columns["start_time"] else ""
    )
    # A timestamp column is optional (the official file has none). If the file
    # does provide one, an unparseable value makes the row invalid.
    if columns["start_time"] and responded_at is None:
        return None

    skill_name = (
        _clean(raw.get(columns["skill_name"])) if columns["skill_name"] else ""
    )
    skill_id = _clean(raw.get(columns["skill_id"])) if columns["skill_id"] else ""
    if not skill_name and not skill_id:
        return None

    assignment_id = (
        _clean(raw.get(columns["assignment"])) if columns["assignment"] else ""
    )
    order_id = _clean(raw.get(columns["order"])) if columns["order"] else ""

    topic_key = (skill_name or f"Skill {skill_id}").casefold()
    # `order_id` is the original problem-log id: it is stable across downloads
    # and distinguishes multiple responses inside one assignment, which the
    # remaining fields cannot do when the file has no timestamps.
    digest_parts = (
        dataset,
        user_id,
        topic_key,
        assignment_id,
        order_id,
        responded_at.isoformat() if responded_at else "",
        "1" if correct else "0",
    )
    digest = hashlib.sha256("\x1f".join(digest_parts).encode("utf-8")).hexdigest()

    return {
        "external_user_id": user_id,
        "skill_name": skill_name,
        "skill_id": skill_id,
        "topic_key": topic_key,
        "correct": correct,
        "responded_at": responded_at,
        "assignment_id": assignment_id,
        "order_id": order_id,
        "hint_count": (
            _parse_int(_clean(raw.get(columns["hints"]))) if columns["hints"] else None
        ),
        "attempt_count": (
            _parse_int(_clean(raw.get(columns["attempts"])))
            if columns["attempts"]
            else None
        ),
        "response_ms": (
            _parse_int(_clean(raw.get(columns["response_ms"])))
            if columns["response_ms"]
            else None
        ),
        "source_row_hash": digest,
    }


def _student_email(external_user_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.+-]", "-", external_user_id).strip("-.")[:64]
    if not safe:
        safe = hashlib.sha1(external_user_id.encode("utf-8")).hexdigest()[:16]
    return f"assistments+{safe}@edumind.local"


def _get_or_create_student(
    db: Session,
    external_user_id: str,
    cache: dict[str, Student],
) -> tuple[Student, bool]:
    student = cache.get(external_user_id)
    if student is not None:
        return student, False

    email = _student_email(external_user_id)
    student = db.scalar(select(Student).where(Student.email == email))
    created = False
    if student is None:
        name = f"ASSISTments student {external_user_id}"[:120]
        student = Student(name=name, email=email)
        db.add(student)
        db.flush()
        created = True

    cache[external_user_id] = student
    return student, created


def _get_or_create_topic(
    db: Session,
    skill_name: str,
    skill_id: str,
    dataset: str,
    cache: dict[str, Topic],
) -> tuple[Topic, bool]:
    raw_name = skill_name or f"Skill {skill_id}"
    name = re.sub(r"\s+", " ", raw_name).strip()[:160]
    if not name:
        name = f"Skill {skill_id}"[:160]

    key = name.casefold()
    topic = cache.get(key)
    if topic is not None:
        return topic, False

    topic = db.scalar(select(Topic).where(func.lower(Topic.name) == name.lower()))
    created = False
    if topic is None:
        topic = Topic(
            name=name,
            description=f"Imported from {dataset}.",
            difficulty=0.5,
        )
        db.add(topic)
        db.flush()
        created = True

    cache[key] = topic
    return topic, created


def import_assistments(
    db: Session,
    csv_path: str | Path,
    *,
    dataset_name: str = "assistments-2009-10",
    max_rows: int | None = None,
    max_skills: int | None = None,
    batch_size: int = 500,
    delimiter: str = ",",
    encoding: str | None = None,
    build_attempts: bool = True,
    progress_every: int = 25_000,
) -> ImportSummary:
    """Import an ASSISTments Skill Builder CSV into EduMind.

    ``max_skills`` limits how many distinct skills become topics; rows for
    additional skills are skipped and counted. This is useful for keeping a
    local demo dashboard readable when using the full dataset.

    If the file has no timestamp column (as with the official 2009-10 Skill
    Builder release), a deterministic synthetic timeline is generated; see
    ``_SyntheticClock``.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if max_skills is not None and max_skills < 1:
        raise ValueError("max_skills must be at least 1")
    if max_rows is not None and max_rows < 1:
        raise ValueError("max_rows must be at least 1")

    summary = ImportSummary(dataset=dataset_name, csv_path=str(path))
    student_cache: dict[str, Student] = {}
    topic_cache: dict[str, Topic] = {}
    created_topic_ids: set[int] = set()
    allowed_skills: set[str] = set()
    groups: dict[tuple[int, int, date], _AttemptGroup] = {}
    batch: list[dict[str, Any]] = []
    clock = _SyntheticClock()

    text_encoding = encoding or _detect_encoding(path)
    logger.info("Reading %s with encoding %s", path, text_encoding)

    lines = _iter_decoded_lines(path, text_encoding)
    with closing(lines):
        reader = csv.DictReader(lines, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header row: {path}")
        columns = _detect_columns(reader.fieldnames)

        def flush_batch() -> None:
            if not batch:
                return

            hashes = [item["source_row_hash"] for item in batch]
            existing = set(
                db.scalars(
                    select(ProblemResponse.source_row_hash).where(
                        ProblemResponse.source == dataset_name,
                        ProblemResponse.source_row_hash.in_(hashes),
                    )
                )
            )

            local_seen: set[str] = set()
            new_rows: list[tuple[ProblemResponse, dict[str, Any]]] = []

            for item in batch:
                digest = item["source_row_hash"]
                if digest in existing or digest in local_seen:
                    summary.duplicate_rows += 1
                    continue
                local_seen.add(digest)

                topic_key: str = item["topic_key"]
                if max_skills is not None and topic_key not in allowed_skills:
                    if len(allowed_skills) >= max_skills:
                        summary.skipped_new_skill_rows += 1
                        continue
                    allowed_skills.add(topic_key)

                student, student_created = _get_or_create_student(
                    db, item["external_user_id"], student_cache
                )
                topic, topic_created = _get_or_create_topic(
                    db,
                    item["skill_name"],
                    item["skill_id"],
                    dataset_name,
                    topic_cache,
                )
                if student_created:
                    summary.students_created += 1
                if topic_created:
                    summary.topics_created += 1
                    created_topic_ids.add(topic.id)

                response = ProblemResponse(
                    student_id=student.id,
                    topic_id=topic.id,
                    source=dataset_name,
                    source_row_hash=digest,
                    external_user_id=item["external_user_id"],
                    external_skill_id=item["skill_id"] or None,
                    skill_name=item["skill_name"] or None,
                    assignment_id=item["assignment_id"] or None,
                    correct=item["correct"],
                    hint_count=item["hint_count"],
                    attempt_count=item["attempt_count"],
                    response_ms=item["response_ms"],
                    responded_at=item["responded_at"],
                )
                new_rows.append((response, item))

            batch.clear()
            if not new_rows:
                return

            db.add_all([response for response, _ in new_rows])
            db.flush()

            for response, item in new_rows:
                group_key = (
                    response.student_id,
                    response.topic_id,
                    item["responded_at"].date(),
                )
                group = groups.setdefault(group_key, _AttemptGroup())
                group.total += 1
                group.correct += 1 if item["correct"] else 0
                if group.last_at is None or item["responded_at"] > group.last_at:
                    group.last_at = item["responded_at"]
                group.response_ids.append(response.id)

            summary.inserted_responses += len(new_rows)

        for line_number, raw in enumerate(reader, start=2):
            if max_rows is not None and summary.rows_read >= max_rows:
                break
            summary.rows_read += 1

            item = _parse_row(raw, columns, dataset_name)
            if item is None:
                summary.invalid_rows += 1
                if len(summary.invalid_examples) < 5:
                    summary.invalid_examples.append(f"line {line_number}")
                continue

            if item["responded_at"] is None:
                item["responded_at"] = clock.next_timestamp(
                    item["external_user_id"],
                    item["assignment_id"],
                    item["response_ms"],
                )
                summary.synthetic_timestamps += 1

            batch.append(item)
            if len(batch) >= batch_size:
                flush_batch()

            if progress_every and summary.rows_read % progress_every == 0:
                logger.info(
                    "Read %s rows, inserted %s responses",
                    summary.rows_read,
                    summary.inserted_responses,
                )

        flush_batch()

    if build_attempts:
        for (student_id, topic_id, _day), group in sorted(
            groups.items(), key=lambda pair: (pair[0][0], pair[0][1], pair[0][2])
        ):
            if group.total == 0 or group.last_at is None:
                continue
            attempt, _mastery = apply_quiz_attempt(
                db,
                student_id=student_id,
                topic_id=topic_id,
                correct_answers=group.correct,
                total_questions=group.total,
                attempted_at=group.last_at,
                snapshot_at=group.last_at,
            )
            db.execute(
                update(ProblemResponse)
                .where(ProblemResponse.id.in_(group.response_ids))
                .values(quiz_attempt_id=attempt.id)
            )
            summary.attempts_created += 1
            summary.mastery_updates += 1

    # Estimate difficulty for topics created by this import. Existing curated
    # topics keep their hand-set difficulty.
    for topic_id in sorted(created_topic_ids):
        total = db.scalar(
            select(func.count(ProblemResponse.id)).where(
                ProblemResponse.topic_id == topic_id,
                ProblemResponse.source == dataset_name,
            )
        )
        if not total:
            continue
        correct = db.scalar(
            select(func.count(ProblemResponse.id)).where(
                ProblemResponse.topic_id == topic_id,
                ProblemResponse.source == dataset_name,
                ProblemResponse.correct.is_(True),
            )
        )
        topic = db.get(Topic, topic_id)
        if topic is not None:
            topic.difficulty = round(
                clamp(1.0 - float(correct or 0) / float(total), 0.05, 0.95), 4
            )

    db.commit()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import an ASSISTments Skill Builder CSV into EduMind."
    )
    parser.add_argument("--csv", required=True, type=Path, help="Path to the CSV file")
    parser.add_argument(
        "--dataset-name",
        default="assistments-2009-10",
        help="Label stored on imported responses (default: assistments-2009-10)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Only read the first N data rows (useful for a quick trial)",
    )
    parser.add_argument(
        "--max-skills",
        type=int,
        default=None,
        help="Create at most N distinct skill topics; later skills are skipped",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per insert batch (default: 500)",
    )
    parser.add_argument(
        "--delimiter",
        default=",",
        help="CSV delimiter (default: comma)",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help="CSV encoding (default: auto-detect UTF-8, fall back to Latin-1)",
    )
    parser.add_argument(
        "--skip-attempts",
        action="store_true",
        help="Load raw responses only; do not build attempts or mastery",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        try:
            summary = import_assistments(
                db,
                args.csv,
                dataset_name=args.dataset_name,
                max_rows=args.max_rows,
                max_skills=args.max_skills,
                batch_size=args.batch_size,
                delimiter=args.delimiter,
                encoding=args.encoding,
                build_attempts=not args.skip_attempts,
            )
        except Exception as exc:  # noqa: BLE001 - CLI should surface a clean error
            db.rollback()
            logger.error("Import failed: %s", exc)
            return 1

    print(json.dumps(asdict(summary), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
