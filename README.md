# LLM Testing Harness

LLM Testing Harness is a senior capstone project for creating and reviewing repeatable LLM evaluations. The Week 5 prototype runs an inline prompt against a demo or OpenAI-compatible provider, scores it, and saves the test version and run in PostgreSQL.

## Architecture

The project is a modular monolith with three parts:

- A React and TypeScript browser frontend.
- A Python and FastAPI REST backend.
- PostgreSQL as the application system of record for API runs and test versions.

For local development, Docker Compose runs PostgreSQL only. The backend and frontend run directly on the developer's machine.

## Documentation

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Requirements](docs/requirements.md)
- [Contributing](CONTRIBUTING.md)

## Prerequisites

- Python 3.12
- Node.js 22 or later and npm
- Docker with Docker Compose

## Environment setup

Copy `.env.example` to `.env`. The example values match `docker-compose.yml` and are intended only for local development.

The frontend uses `http://localhost:8000` by default. To use another backend address, create `frontend/.env.local` containing:

```text
VITE_API_BASE_URL=http://localhost:8000
```

## Start PostgreSQL

From the repository root:

```shell
docker compose up -d postgres
```

Stop it with `docker compose down`. The named `postgres_data` volume preserves database data between container restarts.

## Backend setup

From the `backend` directory, create and activate a virtual environment:

```shell
python -m venv .venv
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```shell
# macOS or Linux
source .venv/bin/activate
```

Install the application and development dependencies:

```shell
python -m pip install -e ".[dev]"
```

Then apply migrations and start the API:

```shell
alembic upgrade head
uvicorn app.main:app --reload
```

The health endpoint is available at `http://localhost:8000/health`.

The API defaults to a deterministic local demo provider (`LLM_PROVIDER=demo`), so no model key is needed for a local walkthrough. `POST /runs` executes and commits a run, and `GET /runs?limit=20` returns saved results. Every new test gets a stable ID and version 1. Loading a saved test in the UI and changing its prompt or scoring rules creates the next version; changing its model or temperature keeps the test version and creates another run. The returned `metadata.test_id` and `metadata.test_version` identify what was saved.

## Frontend setup

From the `frontend` directory:

```shell
npm install
npm run dev
```

Open `http://localhost:5173`. Run a test, refresh the browser, and check that the saved result remains visible. Use **Load this test into the form** to create a new run or revision, or **Start a new test** to create an unrelated test.

Run the React page with the FastAPI server above. The separate `backend/demo.py` and `backend/demo_static` demo still use their original JSONL file and do not write to PostgreSQL.

## Verification

Run backend tests and checks from `backend`:

```shell
pytest
ruff check .
ruff format --check .
```

Run the frontend build validation from `frontend`:

```shell
npm run build
```

Validate the Compose configuration from the repository root:

```shell
docker compose config
```

The backend run persistence and history tests require a migrated PostgreSQL instance. The CI job starts Postgres and applies migrations before running them.
