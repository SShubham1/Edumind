# EduMind

EduMind is a local-first adaptive learning platform. It tracks per-topic mastery from
study sessions and quiz results, ranks what each student should study next, visualises
progress, and generates study plans and flashcards with a server-side LLM (with a
deterministic fallback when no key is configured).

This is a boilerplate implementation of the CS698B project proposal. Cross-development
plugin endpoints for HomeSolar are intentionally deferred until the collaboration
contract is agreed.

## Features

- **Students and topics** with seeded demo data.
- **ASSISTments ETL** that imports real historical responses from the 2009-10 Skill
  Builder CSV, stores them in `problem_responses`, and rebuilds attempts and mastery.
- **Study logging** and **quiz results** that update mastery.
- **Simplified Bayesian Knowledge Tracing** for per-topic mastery estimates.
- **Explainable recommendations** using
  `R(t) = w1(1-M) + w2F + w3D + w4W` (mastery, revision urgency, difficulty, recent
  weakness), with a reason and contribution breakdown per topic.
- **Mastery dashboard** with a bar chart, mastery-over-time line chart, and accessible
  data-table views.
- **AI study plans** generated server-side from ranked topics.
- **Flashcards** generated per topic by the LLM, validated as JSON before saving, with
  deterministic retrieval-practice cards as a fallback.
- **OpenAPI docs** at `/docs`.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite, Plotly |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2 |
| Database | SQLite now; PostgreSQL-compatible models |
| LLM | Any OpenAI-compatible chat-completions API, configured server-side |

## Repository layout

```text
Edumind/
├── backend/
│   ├── app/
│   │   ├── config.py            # environment settings
│   │   ├── database.py          # engine, session, Base
│   │   ├── models.py            # students, topics, records, mastery, flashcards, ...
│   │   ├── schemas.py           # request/response models
│   │   ├── seed.py              # demo data
│   │   ├── main.py              # FastAPI app and lifespan
│   │   ├── routers/             # health, topics, students, records, flashcards
│   │   ├── etl/                 # ASSISTments CSV importer and CLI
│   │   └── services/            # mastery, progress, recommendations, llm
│   ├── data/
│   │   └── sample_assistments.csv   # tiny committed fixture for the ETL
│   ├── tests/                   # pytest service, API and ETL tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # dashboard composition
│   │   ├── api.ts               # typed API client
│   │   ├── components/          # charts, recommendations, forms, flashcards
│   │   └── styles.css
│   └── package.json
└── README.md
```

## Quick start

Run the backend and frontend in two terminals.

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional; defaults work without it
uvicorn app.main:app --reload --port 8000
```

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- On first start, the app creates `edumind.db` and seeds demo data when
  `SEED_DEMO_DATA=true`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to `http://localhost:8000`.

### Demo data

| Student | Email | Notes |
|---|---|---|
| Demo Student | demo@edumind.local | Quiz history, study sessions, sample flashcards |
| Asha Rao | asha@edumind.local | Quiz history, study session, sample flashcards |

Five topics are seeded: Arrays and Lists, Binary Trees, Graphs, Dynamic Programming,
Probability.

## ASSISTments dataset (ETL)

The importer streams the **ASSISTments 2009-10 Skill Builder** CSV into EduMind. It
does not bundle the dataset; download it yourself and convert it to CSV if needed.

### Get the data

The dataset is published by ASSISTments at
<https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data>
(`skill_builder_data.csv`, plus the newer
`skill_builder_data_corrected/skill_builder_data_corrected.csv` re-release). Place the
file in `backend/data/` — for example `backend/data/skill_builder_data.csv`. Real
dataset files are gitignored; only `backend/data/sample_assistments.csv` is committed.

The original release contains roughly 525k response rows, 4.2k students, 3.5k
assignments and 111 skill labels. About 79k rows have an empty `skill_name` (they belong
to non-skill-builder problem sets) and are skipped as invalid. The file has **no
timestamp column**; `order_id` is chronological and is used to build a synthetic
timeline. It also contains a few non-UTF-8 bytes, so the importer auto-detects UTF-8
and falls back to Latin-1.

### Run the import

```bash
cd backend
.venv/bin/python -m app.etl.assistments --csv data/skill_builder_data.csv
```

For a quick trial that keeps the dashboard readable:

```bash
# First 50k rows only
.venv/bin/python -m app.etl.assistments --csv data/skill_builder_data.csv --max-rows 50000

# Only the first 10 skills become topics; responses for later skills are skipped
.venv/bin/python -m app.etl.assistments --csv data/skill_builder_data.csv --max-skills 10
```

The CLI creates the tables if they do not exist, commits in batches, and prints a JSON
summary:

```json
{
  "rows_read": 17,
  "inserted_responses": 13,
  "duplicate_rows": 1,
  "invalid_rows": 3,
  "skipped_new_skill_rows": 0,
  "students_created": 3,
  "topics_created": 3,
  "attempts_created": 5,
  "mastery_updates": 5,
  "synthetic_timestamps": 0
}
```

| Flag | Purpose |
|---|---|
| `--csv PATH` | Required input CSV |
| `--dataset-name NAME` | Label stored on responses; default `assistments-2009-10` |
| `--max-rows N` | Read only the first N data rows |
| `--max-skills N` | Create at most N skill topics |
| `--batch-size N` | Insert batch size; default `500` |
| `--delimiter CHAR` | CSV delimiter; default `,` |
| `--encoding NAME` | Override encoding; default auto-detect (UTF-8, then Latin-1) |
| `--skip-attempts` | Store raw responses only; skip attempt/mastery building |

### What the pipeline does

1. **Extract / validate** — detects the official headers (and common re-exports),
   requires `user_id`, `correct`, and either `skill_name` or `skill_id`. Rows with
   unparseable correctness, a missing user or skill, or an unreadable timestamp *when
   the file provides one* are counted as invalid and skipped.
2. **Transform** — external users become anonymised students
   (`assistments+<user_id>@edumind.local`), skills become topics, and each valid row
   becomes a `problem_responses` record.
3. **Deduplicate** — each row gets a SHA-256 identity over dataset, user, skill,
   assignment, order ID, timestamp, and correctness. Re-importing the same file inserts
   nothing. Multi-skill problems appear once per skill with the same `order_id`; the
   skill is part of the identity, so both rows are kept.
4. **Build attempts** — responses are grouped per student, topic, and calendar day into
   quiz attempts. Mastery snapshots use the original attempt time (or the synthetic
   one), so history stays chronological instead of appearing as today.
5. **Estimate difficulty** — topics created by the import get
   `difficulty = 1 - accuracy` (clamped to `0.05..0.95`). Curated topics keep their
   hand-set difficulty.

The frontend and API then work unchanged: imported topics appear in `/api/topics`, and
imported students get `/mastery`, `/mastery-history`, `/progress`, and
`/recommendations` from real responses.

### Notes

- Importing into a database that already has demo data simply adds the imported
  students and topics alongside it. To show **only** imported data, start from an empty
  database and set `SEED_DEMO_DATA=false`.
- **Synthetic dates:** because the official file has no timestamps, imported history is
  placed on a deterministic 2010 timeline. Each new assignment advances one day, and
  responses inside an assignment advance by their recorded response time. The dates are
  internally consistent and reproducible, but they are not real calendar dates.
- A full import creates ~4.2k students and 111 topics, all returned by
  `GET /api/students` and `/api/topics`. Use `--max-rows` / `--max-skills` for a
  dashboard-sized demo until the student picker is paginated or searchable.
- Re-running with different flags (for example a different `--dataset-name`) creates a
  separate set of response rows, because the dataset label is part of the identity.
- The import is idempotent for the same file and label, but it is not a
  change-data-capture sync: corrected rows with new timestamps or order IDs count as
  new responses.
- The importer uses the standard library `csv` module and SQLAlchemy, so it runs without
  pandas or numpy.

## API

Base path: `/api`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET / POST | `/api/topics` | List or create topics |
| GET / POST | `/api/students` | List or create students |
| GET | `/api/students/{id}` | Student details |
| GET | `/api/students/{id}/mastery` | Per-topic mastery |
| GET | `/api/students/{id}/mastery-history` | Mastery snapshots over time |
| GET | `/api/students/{id}/progress` | Dashboard totals and mastery rows |
| GET | `/api/students/{id}/recommendations?limit=5` | Ranked topics with reasons |
| POST | `/api/students/{id}/study-plan` | LLM study plan (fallback supported) |
| POST | `/api/study-records` | Log a study session |
| GET | `/api/students/{id}/study-records` | Recent study sessions |
| POST | `/api/quiz-results` | Submit a quiz result and update mastery |
| GET | `/api/students/{id}/quiz-results` | Recent quiz attempts |
| GET | `/api/students/{id}/flashcards?topic_id=` | List a student's flashcards |
| POST | `/api/flashcards` | Create a flashcard manually |
| DELETE | `/api/flashcards/{id}` | Delete a flashcard |
| POST | `/api/students/{id}/flashcards/generate` | Generate and save flashcards for a topic |

Example flashcard generation:

```bash
curl -X POST http://localhost:8000/api/students/1/flashcards/generate \
  -H "Content-Type: application/json" \
  -d '{"topic_id": 4, "count": 5}'
```

The response includes `source: "llm" | "fallback"`, so callers can see whether the
language model or the deterministic generator produced the cards.

## Configuration

Copy `backend/.env.example` to `backend/.env` and adjust as needed.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./edumind.db` | SQLAlchemy URL; use `postgresql+psycopg://...` for PostgreSQL |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Comma-separated allowed origins |
| `SEED_DEMO_DATA` | `true` | Seed demo data on first start |
| `BKT_PRIOR` / `BKT_LEARN` / `BKT_GUESS` / `BKT_SLIP` | `0.30` / `0.18` / `0.20` / `0.10` | Simplified BKT parameters |
| `REC_WEIGHT_*` | `0.45` / `0.20` / `0.15` / `0.20` | Recommendation weights |
| `REVISION_WINDOW_DAYS` | `14` | Days until revision urgency saturates |
| `LLM_API_KEY` | unset | Server-side API key; never expose to the browser |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL` | `gpt-4o-mini` | Chat-completions model |

Without `LLM_API_KEY`, study plans and flashcards use deterministic fallbacks.

## Tests

```bash
cd backend
.venv/bin/pytest -q
```

The suite covers the API, mastery/recommendation services, and the ASSISTments ETL
(valid rows, invalid rows, duplicates, idempotency, skill limits, and missing columns).

Frontend build:

```bash
cd frontend
npm run build
```

## Design notes and limitations

- **Mastery:** a single step of Bayesian Knowledge Tracing is blended by attempt score,
  rather than fitting a full pyBKT model. BKT parameters are global hand-set defaults,
  not fitted per topic. The service boundary allows replacing them later.
- **Dataset:** the ASSISTments importer stores real historical responses and drives
  mastery from them, but there is no held-out evaluation comparing BKT against a
  baseline yet. Attempts are aggregated per student, topic, and day for the dashboard;
  the underlying `problem_responses` rows are retained for future per-response models.
- **Recommendations:** weights start hand-set; `recommendation_logs` and `model_runs`
  tables exist for learning weights from outcomes.
- **LLM safety:** keys live only in the backend environment. Generated flashcards are
  parsed and validated before being persisted; malformed output falls back safely.
- **Auth:** not implemented yet. Add authentication before any real deployment.
- **Database:** SQLite is used locally; models avoid SQLite-specific types so PostgreSQL
  can be enabled through `DATABASE_URL` (install `psycopg` when needed).
- **Docker:** intentionally not included at this stage.
- **Cross-dev plugin:** HomeSolar endpoints and registration hooks are deferred until the
  collaboration API contract is available.
