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

The API defaults to a deterministic local demo provider (`LLM_PROVIDER=demo`), so no model key is needed for a local walkthrough. `POST /runs` requires a `test_name`, executes the evaluation, and commits the run. `GET /runs?limit=100` returns recent saved results. Every new test gets a stable ID and version 1. Changing its name, prompt, or scoring rules creates the next version; changing only its model or temperature makes another run of the selected version. The returned `metadata.test_id`, `metadata.test_version`, and `metadata.test_name` identify what was saved. Migration `0003_version_names` gives preexisting versions their original test name.

## Frontend setup

From the `frontend` directory:

```shell
npm install
npm run dev
```

Open `http://localhost:5173`. Enter a test name and prompt, then click **Run and save test**. Refresh the browser; the run remains in the collapsible **Saved runs** sidebar. Double-click a named run (or focus it and press Enter) to restore its inputs and view its stored result. Change the test name or a scoring rule and save again to create a new version; earlier runs keep their original names. Use **New test** to start an unrelated test. The sidebar displays the 100 most recent saved runs for this prototype.

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
