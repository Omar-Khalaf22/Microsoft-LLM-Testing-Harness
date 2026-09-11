# LLM Testing Harness

LLM Testing Harness is a senior capstone project for creating and reviewing repeatable LLM evaluations. This repository currently contains only the Phase 0 application foundation; model calls, evaluation tasks, scoring, and run orchestration have not been implemented.

## Architecture

The project is a modular monolith with three parts:

- A React and TypeScript browser frontend.
- A Python and FastAPI REST backend.
- PostgreSQL as the future application system of record.

For local development, Docker Compose runs PostgreSQL only. The backend and frontend run directly on the developer's machine.

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

## Frontend setup

From the `frontend` directory:

```shell
npm install
npm run dev
```

Open `http://localhost:5173`. The page calls the backend health endpoint and displays its status.

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

The backend health tests do not need a running PostgreSQL instance. Database integration tests will be added when Phase 1 introduces application data.
