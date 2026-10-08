# Local laptop demo integration

Branch: `codex/laptop-demo-integration` (no upstream, no new commits, no pushes).
Worktree: `C:\Users\vashi\.codex\worktrees\laptop-demo-integration\LLM Testing Harness Team`.
All implementation changes are uncommitted in this worktree. Existing main, pranjal-runs, and temp-pranjal-ahmad-integration worktrees were left intact.

## Integrated sources

- Omar: `origin/omar-db-history-integration-2`, `b8b310fd129fbd037f14e143b1b70223d7274d25`. This is the new branch base: PostgreSQL models/repositories/migrations, named tests, named versions, React/API history and saved-run sidebar.
- Lina: `origin/lina-updated-ui`, `fd024677eab2048c370c551ec8dfa85c54063e43`. Latest static design/scoring controls ported into Omar's existing React adaptation of her cream/green layout. Six configurable weights, total-100 feedback, ratios, rounding and objective pass threshold run through the backend. The three static reference files match Lina's branch; they are not loaded by React or FastAPI.
- Pranjal: `origin/pranjal-runs`, `9562708fe7e572607678a28c7a74ade7f57fc723` is a common ancestor. Existing OpenAICompatibleProvider and request model forwarding retained. Local uncommitted Settings/SecretStr/provider-selection work carried over from the pranjal-runs worktree, with tests adapted to PostgreSQL.
- Pranjal/Ahmad: existing React/OpenAI integration inspected. Its uncommitted dark UI was preserved in its original worktree; it was not substituted for Lina's requested latest design. No teammate refs were moved.

The laptop execution path is React -> POST /runs -> Settings-selected provider -> TestExecutor -> backend objective scoring -> transactional PostgreSQL save -> RunResponse. GET /runs loads committed rows. There is no browser response generator or browser scoring in this path. Do not launch backend/demo.py for this demo: it is the historical standalone simulator. Its automatic sample suite was not ported into a paid-model batch.

## Start on this laptop: tested native PostgreSQL fallback

Docker Desktop launched, but its engine did not respond. A separate PostgreSQL 18.4 cluster was initialized under ignored `.demo-postgres`, bound to 127.0.0.1:55433. It does not use either existing Windows PostgreSQL service. It uses loopback-only local-development trust authentication. `llm_harness_test` contains mocked verification data; `llm_harness_demo` is separately migrated and empty. Do not run tests against the demo database.

PowerShell terminal 1:

```powershell
$demoRoot = 'C:\Users\vashi\.codex\worktrees\laptop-demo-integration\LLM Testing Harness Team'
$python = 'C:\Users\vashi\.codex\worktrees\pranjal-runs\LLM Testing Harness Team\backend\.venv\Scripts\python.exe'
$pgBin = 'C:\Program Files\PostgreSQL\18\bin'
& "$pgBin\pg_ctl.exe" -D "$demoRoot\.demo-postgres" status
if ($LASTEXITCODE -ne 0) {
    & "$pgBin\pg_ctl.exe" -D "$demoRoot\.demo-postgres" -l "$demoRoot\.demo-postgres\server.log" -o '-h 127.0.0.1 -p 55433' -w start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not start.' }
}
$env:DATABASE_URL = 'postgresql+psycopg://llm_harness@127.0.0.1:55433/llm_harness_demo'
# Reference the existing ignored file; do not copy or print it.
$env:LLM_ENV_FILE = 'C:\Users\vashi\.codex\worktrees\pranjal-runs\LLM Testing Harness Team\backend\.env'
if (!(Test-Path -LiteralPath $env:LLM_ENV_FILE)) { throw 'Existing backend environment file is missing.' }
$env:LLM_PROVIDER = 'openai'
$env:OPENAI_BASE_URL = 'https://api.openai.com/v1'
$env:CORS_ORIGINS = '["http://localhost:5173"]'
Set-Location "$demoRoot\backend"
$env:PYTHONPATH = (Get-Location).Path
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migration failed; do not start the demo.' }
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The existing virtualenv is reused as a Python runtime only; app imports resolve to the new worktree. Restart the API after changing configuration because Settings is cached. Process environment takes precedence over the selected dotenv file. The key stays SecretStr until constructing the backend provider. Do not set a VITE variable containing a key. To use the no-key provider, change LLM_PROVIDER to demo and restart; results identify local_demo.

PowerShell terminal 2:

```powershell
Set-Location 'C:\Users\vashi\.codex\worktrees\laptop-demo-integration\LLM Testing Harness Team\frontend'
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed.' }
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev -- --host localhost --port 5173 --strictPort
```

PowerShell terminal 3:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Start-Process 'http://localhost:5173'
# Optional Swagger:
Start-Process 'http://127.0.0.1:8000/docs'
```

Use localhost:5173, matching CORS. Stop an old server occupying 8000/5173 in its own terminal before starting these. No existing servers were stopped for this integration.

## Docker Compose alternative

After Docker Desktop's engine is healthy, this uses the project's PostgreSQL 16 image in an isolated Compose project/volume and loopback port 55432, avoiding existing port 5432 databases. Modern Compose supporting !override is required (installed Compose 5.3 parsed it successfully).

```powershell
Set-Location 'C:\Users\vashi\.codex\worktrees\laptop-demo-integration\LLM Testing Harness Team'
docker compose -p llm-laptop-demo -f docker-compose.yml -f docker-compose.demo.yml up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'Docker PostgreSQL is not ready.' }
$env:DATABASE_URL = 'postgresql+psycopg://llm_harness:local-development-only@127.0.0.1:55432/llm_harness'
```

Then run terminal 1's configuration/migration/uvicorn commands from `$env:LLM_ENV_FILE` onward, defining demoRoot/python first. Do not overwrite DATABASE_URL with the native value. The Compose password above is the existing public development-only placeholder, not a secret. Native and Docker databases are separate; history does not transfer between them automatically. Docker container startup/PG16 remain unverified because the engine was unresponsive; native PG18 startup/migrations/persistence were verified.

## Final API contract

POST /runs requires test_name (1-100 chars) and prompt (1-10000 chars). Additional fields/defaults:

- model: nonempty model ID, default gpt-4.1-mini; forwarded unchanged to the provider. Returned model may be the provider's resolved/snapshot ID.
- temperature: finite 0..2, default 0.2.
- expected_keywords / forbidden_terms: arrays of up to 20 nonempty strings, default [].
- minimum_length: integer 0..10000, API default 40; minimum_sentences: integer 1..20, API default 2. React explicitly starts at Lina's 80 and 3.
- weights: finite numeric keyword/relevance/length/sentences/forbidden/valid, each 0..100, sum100 (floating tolerance 1e-8); default 30/20/15/15/10/10. Numeric strings and unknown fields are rejected. Zero disables contribution, not the individual criterion's informational pass flag.
- test_id optional; omit to create a new named test. test_version optional positive integer requires test_id. Selecting a saved version and rerunning unchanged uses that version; changed name/prompt/criteria/weights creates latest+1. Model/temperature changes create another run, not a version. Missing selected identity/version returns404 before model generation.

```json
{
  "test_name": "Multiplexer explanation",
  "prompt": "Explain what a multiplexer does.",
  "model": "gpt-4.1-mini",
  "temperature": 0.2,
  "expected_keywords": ["input", "output", "select"],
  "minimum_length": 80,
  "minimum_sentences": 3,
  "forbidden_terms": [],
  "weights": {"keyword":30,"relevance":20,"length":15,"sentences":15,"forbidden":10,"valid":10}
}
```

Response: id, status, prompt, model, provider, response, score (0..100), passed (score>=75), criteria [{name,passed,score,detail}], latency_ms, created_at (UTC completion timestamp), metadata. Metadata includes requested_model, temperature, original criteria inputs, scoring_weights, started_at, usage {input_tokens,output_tokens}, schema_version2.0, test_id, test_version, test_name. Each successful response follows a committed save. Failed criteria can still yield overall PASS according to Lina's weighted score. No key or provider configuration is added to persisted metadata or response.

GET /runs?limit=100 returns the same full result objects, newest first. Limit1..100 (default20). React requests100; older rows remain in PostgreSQL but pagination/search is not implemented. Refresh fetches from backend; selecting a saved run restores prompt/model/temperature/criteria/weights/result. Legacy rows without scoring_weights use defaults. Old rows are not rescored or rewritten.

Validation422 precedes provider construction. Provider/storage failures return a generic sanitized500. Upstream calls cannot be rolled back: if a save fails after generation, the UI reports failure and retrying may make another model call. No distributed exactly-once claim is made.

## Database

Omar's unchanged migrations apply in order: 0001_initial (empty baseline), 0002_week5 (tables), 0003_version_names (version name/backfill). Tables: models, tests, test_versions, test_runs, model_responses, evaluation_results; Alembic also maintains alembic_version. Weights fit existing JSON evaluation_definition/configuration, so no new migration is needed. Test version creation and all result writes share one transaction; failure rolls back the new version. Existing parent tests are locked during version numbering. API history normalizes timestamps to UTC, fixing offset-dependent POST/GET mismatch found on the laptop's Eastern-time PostgreSQL instance.

## Verification

- 81 backend tests pass on real isolated PostgreSQL18.4. All OpenAI transport mocked; no real OpenAI call or credential used.
- Fresh migrations applied successfully to separate empty test/demo databases through0003.
- Ruff check passes; Ruff format --check:39 files formatted.
- React TypeScript + Vite production build passes (33 modules). No frontend lint script is configured; no frontend lint pass is claimed.
- Browser: API health/ready and CORS; invalid weight total disables submit; custom weights20/20/15/15/10/20 submit through OpenAICompatibleProvider with mocked HTTP; committed saved run scored90; reload retained it; selecting restored exact inputs and result. Browser mock server was test-only, outside the repo, using test DB.
- Automated persistence tests inspect committed rows from independent sessions, compare fresh-app GET to POST exactly, change weights to create version2, rerun selected version1, change temperature without new version, and verify rollback/sanitized failure.
- Settings tests cover explicit external dotenv path, environment precedence, demo default, SecretStr, model forwarding, invalid-body ordering, and key-free results/errors.
- Tests emit 12 existing-style collection/deprecation warnings (Test* domain classes, Starlette/httpx/anyio); no failures.
- Docker Compose config parses; Docker engine/container startup still blocked. Real key validity/account quota/model access intentionally not verified.

## Manual real-model demonstration

1. Start the actual API and frontend using the commands above (not the temporary browser-test server). GET /health should return ok; the fresh demo DB starts with empty history.
2. Enter a unique test name and your own prompt; choose a model available to your OpenAI account, e.g. gpt-4.1-mini. Set weights totaling100 and click Run and save test once. This is the first real paid-model call, performed by you.
3. Inspect provider=openai_compatible, requested_model, returned model, real response, usage, run id and test/version in Structured JSON. The test-only text MOCK TRANSPORT CHECK must not appear. Provider labeling alone was also used by mocked tests, so run the normal app.main:app command above.
4. Refresh the browser and select that saved item. Confirm the same run id/response/weights. GET http://127.0.0.1:8000/runs?limit=100 returns it independently of React state.
5. Stop/restart FastAPI and Vite, refresh and select again; same PostgreSQL run remains. Optionally inspect test_runs/model_responses/evaluation_results using your database client.
6. Change a scoring weight and balance the total; rerun to create version2. Select version1 and confirm its original scoring inputs/result remain. Changing temperature alone creates another run on the selected version.

No API key was printed, read into implementation tooling, copied, staged or committed. Existing ignored configuration is only referenced by path for your runtime launch.

## Files changed relative to Omar's branch base

- `.env.example`
- `.gitignore`
- `backend/app/config.py`
- `backend/app/evaluation/executor.py`
- `backend/app/evaluation/models.py`
- `backend/app/evaluation/scoring.py`
- `backend/app/evaluation/weights.py`
- `backend/app/repositories/prototype_runs.py`
- `backend/app/routes/runs.py`
- `backend/app/schemas/runs.py`
- `backend/app/services/run_service.py`
- `backend/demo_static/app.js`
- `backend/demo_static/index.html`
- `backend/demo_static/styles.css`
- `backend/tests/test_demo_integration.py`
- `backend/tests/test_runs.py`
- `docker-compose.demo.yml`
- `docs/LAPTOP_DEMO.md`
- `frontend/src/api.ts`
- `frontend/src/App.css`
- `frontend/src/App.tsx`
- `frontend/src/RunForm.tsx`
- `frontend/src/SavedRuns.tsx`

## Files inherited from Omar relative to pranjal-runs

- `.github/workflows/ci.yml`
- `README.md`
- `backend/alembic/env.py`
- `backend/alembic/versions/0002_week5_schema.py`
- `backend/alembic/versions/0003_test_version_names.py`
- `backend/app/evaluation/executor.py`
- `backend/app/evaluation/models.py`
- `backend/app/evaluation/repository.py`
- `backend/app/import_run.py`
- `backend/app/models/__init__.py`
- `backend/app/models/evaluation.py`
- `backend/app/models/model.py`
- `backend/app/models/run.py`
- `backend/app/models/test.py`
- `backend/app/repositories/__init__.py`
- `backend/app/repositories/prototype_runs.py`
- `backend/app/repositories/runs.py`
- `backend/app/routes/runs.py`
- `backend/app/schemas/runs.py`
- `backend/app/seed.py`
- `backend/app/services/run_service.py`
- `backend/tests/test_prototype_history.py`
- `backend/tests/test_run_persistence.py`
- `backend/tests/test_runs.py`
- `examples/run_result.json`
- `frontend/src/App.css`
- `frontend/src/App.tsx`
- `frontend/src/RunForm.tsx`
- `frontend/src/RunResults.tsx`
- `frontend/src/SavedRuns.tsx`
- `frontend/src/api.ts`
