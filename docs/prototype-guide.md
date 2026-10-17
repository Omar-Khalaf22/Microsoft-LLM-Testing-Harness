# Prototype guide

## Which branch should I use?

| Branch | Purpose |
| --- | --- |
| `main` | Application foundation and the project documentation landing page. Its application code is not the integrated prototype. |
| `omar-db-history-integration-2` | Integrated run form, results/history interface, PostgreSQL persistence, migrations, and import support. Use this branch for the walkthrough below. |
| `week5-integrated` / `backend-scoring` | Earlier integrated execution/scoring work. |

This guide describes the inspected `omar-db-history-integration-2` implementation, whose application-code snapshot was `b8b310fd129fbd037f14e143b1b70223d7274d25` when reviewed on October 16, 2026. Documentation updates do not merge feature branches or change the team's integration process.

## Option 1: browser demo without PostgreSQL

This is the quickest way to explore the model-execution and scoring flow. The default provider generates deterministic sample text; it does not call a real LLM.

Prerequisites: Git and Python 3.12.

```bash
git clone --branch omar-db-history-integration-2 https://github.com/Omar-Khalaf22/Microsoft-LLM-Testing-Harness.git
cd Microsoft-LLM-Testing-Harness/backend
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Then install dependencies and start the demo:

```bash
python -m pip install -e ".[dev]"
python demo.py
```

Open **http://127.0.0.1:8000**. Run a prompt using the demo provider and inspect the response, criterion breakdown, score, timing, and recent results. Strong, partial, and failing sample variants allow the scoring behavior to be compared.

This entry point writes results to `backend/data/results.jsonl`. It does not exercise the React interface or PostgreSQL history. Its HTTP routes are `/api/health`, `/api/run`, and `/api/results`.

## Option 2: integrated React + FastAPI + PostgreSQL workflow

Additional prerequisites: Node.js 22 or later, npm, and Docker with Docker Compose. Check out the same branch as Option 1.

From the repository root:

```bash
cp .env.example .env
docker compose up -d postgres
```

On Windows PowerShell, use `Copy-Item .env.example .env` for the copy step. The provided database credentials are local-development examples.

In a backend terminal, create/activate the Python environment as above, then run:

```bash
cd backend
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. FastAPI is available at **http://localhost:8000**, with API documentation at `/docs`.

Walk through the prototype:

1. Enter a test name, prompt, model, and supported scoring inputs.
2. Execute using the default demo provider.
3. Inspect the response, total, and per-criterion explanations.
4. Reload the interface and retrieve the saved run from history.
5. Change a test definition and inspect its version linkage in the saved evidence.

The React application uses `GET /runs` and `POST /runs`. Its API defaults to `http://localhost:8000`; `VITE_API_BASE_URL` can override this through `frontend/.env.local`.

### Optional real model calls

The inspected provider supports an OpenAI-compatible chat-completions endpoint. Set the following in the backend process environment before starting either server:

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY="your-own-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

For PowerShell, use `$env:LLM_PROVIDER="openai"` and the same `$env:NAME="value"` form for the other variables. Select a model available from that endpoint. Calls use the account and pricing associated with that endpoint.

Provider selection reads process environment variables directly; placing these provider variables only in the application `.env` file does not export them into the process. The default `demo` provider needs no key.

## Verification

From `backend`, the evaluation-only checks can run without a database or model API calls:

```bash
python -m unittest discover -s tests -p test_evaluation.py -v
```

For the complete backend suite, start PostgreSQL, configure the local environment, and apply migrations first:

```bash
pytest
ruff check .
ruff format --check .
```

Persistence tests create database records. Use a disposable local development database for testing. Some tests use provider mocks rather than real network calls.

From `frontend`:

```bash
npm run build
```

The repository includes provider-contract, request-validation, scoring, persistence, and history tests. The October 16 documentation refresh verified the five existing evaluation-only tests and the demo HTTP workflow; it did not re-run PostgreSQL integration, frontend build, real-provider, or cloud-deployment checks.

## Implementation boundaries

- The six prototype checks measure keyword coverage, prompt-term overlap, minimum character count, sentence count, forbidden terms, and nonempty response. They do not establish factual correctness or general model quality.
- The prototype uses fixed point allocations and legacy `passed` fields. SRS v2.0 instead specifies editable criterion maxima totaling 100, numerical results, and separate human assessments.
- Usage is endpoint-dependent. The final design requires unknown usage to remain distinguishable from measured zero; the prototype provider currently defaults missing usage to zero.
- Automated price calculation, full suites/regression, assisted criteria publication, the expanded evaluator catalog, human-rating workflows, authentication, and Azure delivery are not claimed complete here.

For the intended final behavior, see [requirements](requirements.md), [architecture](architecture.md), and [data model](data-model.md).
