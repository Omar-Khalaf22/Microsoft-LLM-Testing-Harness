# Integrated criteria recommendation assistant

## Checkout and preservation

Integration is in `.integration/prototype-2-assistant`, on the local branch
`codex/assistant-registry-integration`, based on `origin/prototype-2-lina` at
`e9fafc01d6323e6c934a928552735428bf614557`. The original checkout stays on
`main`, with its earlier assistant and unrelated changes intact. All 37 preexisting
modified/untracked files were backed up in `.integration/pre-integration-work.zip`
and verified unchanged against `.integration/preserved-files.json` SHA-256 hashes.

## Registry integration

The existing assistant schemas, service, provider, and route were reused. The
replacement for the unavailable-registry stub is `RuntimeCriteriaRegistry` in
`backend/app/assistant/registry.py`. It calls:

- `app.evaluation.registry.list_supported_criteria()` for the executable catalog.
  Entries must also have supported status and an evaluator identifier.
- `app.evaluation.registry.validate_criterion(id, parameters)` for authoritative
  validation. That function internally calls `get_criterion()` and rejects unknown,
  planned, malformed, missing, extra, or invalid parameters.

The adapter translates catalog type labels (`list[str]`, `str`, `int`) into closed
JSON object schemas, without duplicating a list of supported IDs or parameter names.
Unknown future type labels fail closed until the adapter is updated. The registry
remains the authority for value constraints such as nonnegative counts and
`minimum_sentences.count >= 1`. The registry, catalog, dispatcher, and evaluators
were not changed. The existing `assistant/prompts.py`, model-under-test provider,
system-prompt composition, legacy scoring, and persistence were preserved.

The registry blocker is resolved: the real default route returns HTTP 200 for valid
mocked recommendations for each of the 10 executable criteria. All 36 are not yet
supported: 10 supported, 16 planned, 10 absent. See the complete
[contract comparison](assistant-contract-audit.md) for exact naming and placeholder
parameter differences. JSON-only objectives may have no relevant executable criteria
yet; the assistant must not invent support or return irrelevant content checks.

## API and configuration

`POST /assistant/suggest-criteria` accepts required nonempty strings `objective` and
`test_prompt`. It returns `suggestions`, each containing exactly `criterion_id`,
`parameters`, positive integer `maximum_points`, and a nonempty `reason`. IDs must
be unique and points total exactly 100. No API field is renamed to `weight`.

Example request:

```json
{"objective":"The response must contain alpha","test_prompt":"Write a sentence containing alpha."}
```

Example valid response using an executable criterion:

```json
{"suggestions":[{"criterion_id":"required_keywords","parameters":{"keywords":["alpha"]},"maximum_points":100,"reason":"The objective explicitly requires the keyword alpha."}]}
```

The dedicated recommendation system message is separate from model-under-test
instructions. The provider requests JSON Schema output; backend validation remains
mandatory. Every generated ID and parameter object passes the runtime registry
validator before being returned. Suggestions are neither evaluated nor persisted,
and require frontend/user review before execution.

The assistant reuses server-side `OPENAI_API_KEY` and `OPENAI_BASE_URL`. It adds
`ASSISTANT_MODEL` (default `gpt-4o-mini`) and `ASSISTANT_TIMEOUT_SECONDS` (default 30).
Existing `LLM_PROVIDER=demo` still governs model-under-test runs; the recommendation
assistant has no demo fallback. An empty API key returns HTTP 503 with code
`assistant_unconfigured`, distinct from the resolved registry blocker. Provider
errors return controlled 502/504 responses; malformed recommendations return 502.

The final authorized live smoke test returned HTTP 200 from both OpenAI and this
endpoint using `gpt-4o-mini`. For the objective "Ensure the response contains specific
keywords" and prompt "Explain machine learning and mention neural networks.", the
updated instructions produced only `required_keywords` with those two phrases and
`maximum_points: 100`. Executable registry and API contract validation passed.

The instructions require the smallest directly grounded criterion set, prohibit
invented constraints, and allocate points only after selection. Semantic relevance
is model-enforced: this successful live case does not guarantee precision for every
input. No additional model call is needed to run the automated tests.

## Verification and local use

From this worktree's `backend`, with Python 3.12 and a virtual environment:

```powershell
python -m pip install -e ".[dev]"
# Configure DATABASE_URL for an isolated PostgreSQL test database.
python -m alembic upgrade head
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m uvicorn app.main:app --reload
```

Use `/docs` to inspect the endpoint. Configure the API key locally only after live
requests are authorized. The tests do not require real OpenAI credentials.

Verification on 2026-10-22:

- Full backend suite, including database integration and system-prompt regressions:
  **205 passed, 0 failed**. This includes 62 reused assistant test cases and 21 new
  actual-registry integration cases.
- Ruff lint passed; all 53 Python files pass the format check.
- After the precision update, the relevant assistant, actual-registry, and health
  suite passed **88 tests, 0 failed**, including four precision regression cases.
  These mocked cases protect the instructions and response handling; the separate
  live smoke test above verifies the previous over-selection issue for that input.
- `git diff --check` passed. No type checker is configured.
- 11 warnings: existing ORM/test class collection warnings and an installed Starlette
  httpx test-client deprecation. None failed tests.
- Existing migrations were applied to an isolated PostgreSQL 18.4 cluster on localhost
  port 55439, under the ignored root `.venv` directory. No application database was
  modified. CI uses PostgreSQL 16; that version was not tested locally.
- Initial test run had nine fixture errors from inaccessible system temp paths.
  The complete rerun with a workspace-local pytest temp directory passed all tests.

Files added relative to the integration branch:

```text
backend/app/assistant/provider.py
backend/app/assistant/registry.py
backend/app/assistant/schemas.py
backend/app/assistant/service.py
backend/app/routes/assistant.py
backend/tests/test_assistant.py
backend/tests/test_assistant_registry.py
docs/assistant-contract-audit.md
docs/assistant-recommendations.md
```

Files modified: `.env.example`, `backend/app/config.py`, `backend/app/main.py`, and
`backend/pyproject.toml`. Dependencies add runtime `jsonschema` and promote existing
development dependency `httpx` to runtime. No migrations or frontend changes.
