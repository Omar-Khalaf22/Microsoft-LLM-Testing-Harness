# Prototype 3 backend handoff

## Workspace and inspected contracts

Implemented on local `main` at `72099027fcfbc39df5bc2000797a89a9fe658ffd`.
Repository: `Omar-Khalaf22/Microsoft-LLM-Testing-Harness`.
Initial modifications are recorded locally in `.integration/prototype3-initial-status.txt`
(audit-only, deliberately excluded from the publication commit).
Existing modified/untracked work was retained. Only two additive lines in the existing
`backend/app/main.py` register the new router. No commits, merges, pushes or migrations.

Fetched remote branches and read these snapshots without merging them:

- Lina `lina-prototype-3`: `5d8196a6783be8b8e216e96fa64fe22708d6d864`.
- Ahmad `Ahmad-prototype-3`: `4af4aa60a76b9a90ad6c0dc47345eab5fdc6ca12`.
- Omar `omar-db-history-integration-2`: `170b979eb9899e6520cb7eefccac11cb1896a16c`.

The current worktree is the earlier foundation, not the integrated Prototype 2 branch.
An existing `.integration/prototype-2-assistant` tree contains another Prototype 2 snapshot;
it was inspected and left unchanged. Replacing the current backend with a teammate branch
would overwrite existing work, so the new package is isolated in `app/prototype3`.

`lina_rubric.py` and `lina_points.py` are unchanged source copies from Lina's above commit,
respectively `backend/app/evaluation/rubric_judge.py` and `points.py`. They preserve her
validation and rounding rules; these are compatibility snapshots, not competing team contracts.
When integrating into Lina's tree, replace those local imports with her canonical modules.
No human review code or storage is duplicated.

## Implemented behavior

- Separate judge system instructions, model configuration and provider instance. Model-under-test
  instructions and assistant recommendations never become judge system instructions.
- Lina's three supported rubrics: `factual_accuracy`, `completeness`, `evidence_grounding`.
  Each requires reference evidence in this adapter. Unsupported parameters/scales are rejected.
- JSON validation uses Lina's exact four-field output shape: `score`, `rationale`, `evidence`,
  `evaluator_model`. Criterion identity and maximum score come from approved configuration,
  not judge output. Unexpected criterion/maximum fields are rejected. Scores are finite JSON
  numbers from 0 to 1; textual/Boolean scores, missing rationale, fabricated excerpts,
  wrong model identity, refused/truncated responses and provider failures leave scores unavailable.
- Points use Lina's Decimal arithmetic and two-decimal rounding. Allocations total exactly 100.
  The available contract defines a zero-to-one scale. Arbitrary scales, including nonzero minimum
  scales, are deliberately rejected until agreed; no implicit zero-based conversion is performed.
- `ReservedExecutor.execute(run_id)` never allocates an ID or calls a legacy insert repository.
  It validates the saved approved snapshot, claims the reserved record, generates output,
  checkpoints that output, evaluates each criterion and updates the existing final record.
- Generation failure: run `failed`, null total, persisted safe error. Evaluation failure:
  generation run `completed`, evaluation `incomplete`, null total, retained output and successful
  criterion results. An aggregation failure also leaves the total null.
- Timing, effective generation settings, requested/resolved model identities, token usage,
  test identity/version, and rerun link are preserved. Errors do not expose provider exception text.
- Proposed critical policy is separate from Lina's criterion object. Each entry names an approved
  criterion and normalized threshold. Failing a gate sets overall status `failed`, preserving
  the numeric total. With no failed gates, `passed` means the configured gates passed; it does
  not claim an agreed numerical overall pass threshold. Incomplete evaluation is `incomplete`.

## Storage integration: Omar

Implement `Storage` in `backend/app/prototype3/storage.py` by forwarding to your helpers.
No reservation helpers were present in the inspected available branch or fetched main.
The existing `PostgresResultRepository.save` inserts/version-selects records, so it is not
safe to use for reserved executions.

Required operations:

| Operation | Required behavior |
| --- | --- |
| `reserve_test(test_id, test_version, rerun_of)` | Atomically load the exact approved saved version, snapshot configuration, reserve parent and child rows, return IDs. Validate rerun ownership/link. |
| `reserve_suite(suite_id)` | Same atomic reservation for ordered exact-version references; return child IDs in suite order. Raise `NotImplementedError` until available. |
| `execution(execution_id)` | Return parent identity and ordered child IDs. |
| `get(run_id)` | Return an independent copy of the reservation and immutable snapshot, or raise `LookupError`. |
| `claim(run_id)` | Atomic compare-and-set `pending` to `running`, returning the same immutable snapshot; raise `Conflict` on an already claimed/final record. |
| `checkpoint(run)` | Update the existing running record with generated output/usage before evaluations begin. |
| `finish(run)` | Atomically update that existing record with all final results/errors; never insert or replace identity, rerun links or human assessments. |

Each storage write must commit before returning. A failed checkpoint/final write propagates as
503; no success is reported. The saved checkpoint retains generation if final persistence fails.
Crash recovery/leases and retrying final writes remain Omar's storage/worker concern. An existing
running record must not be re-executed blindly. Execution is synchronous with one claim owner;
the routes are not a durable background queue. Storage must enforce any authenticated access
checks before this API is deployed to multiple users. Human assessments are never passed to writes.

## Lina integration

`LinaAdapter` lazily calls your actual `validate_criterion` and `evaluate_criterion` interfaces.
It passes prompt and approved instructions as context. Its point helpers currently use the exact
source snapshots noted above so rubric-only execution works in this earlier worktree.
Deterministic evaluation requires your integrated registry package, which is absent here.
Weights belong to saved approved configuration, not the judge. Final aggregation delegates to
your point arithmetic; any failed criterion prevents a total. Review revisions remain exclusively
owned by your review repository and do not modify automated results.

Please confirm canonical imports, any extension for user-defined scales/rubrics, and critical
policy representation. No guessed fields were added to your catalog, review models or database.

## Provisional API: Ahmad

Existing routes remain unchanged. These isolated routes are mounted at `/prototype3`; they
are provisional and require agreement before frontend adoption. The default app returns 503
until its `app.state.reserved_executor` is configured. No live provider is configured by default.

| Method/path | Request / result |
| --- | --- |
| POST `/prototype3/executions/test` | `{ "test_id": "...", "test_version": 2, "rerun_of": null }` → 201 `{ "id": "parent", "run_ids": ["child"] }` |
| POST `/prototype3/executions/suite` | `{ "suite_id": "..." }` → same ordered reservation shape; 501 if helper unavailable |
| GET `/prototype3/executions/{id}` | Parent ID and ordered child IDs |
| POST `/prototype3/runs/{id}/execute` | No configuration overrides; synchronously executes reserved snapshot and returns final `Run` |
| GET `/prototype3/runs/{id}` | Current state, snapshot, response, usage, evaluation breakdown and nullable total |

After reservation, execute each returned run ID (in order for suites), then retrieve each run for
status/results. A generation/evaluation failure returns a stored result with HTTP 200 and explicit
state/error fields. Request/storage errors use `detail: {code, message}`: 404 missing record,
409 claimed/final run, 422 invalid saved/request configuration, 501 unavailable operation,
503 unconfigured/storage failure. Reservation POST is not idempotent unless Omar supplies a key
policy; retrying it may reserve another execution. `execute` claims prevent duplicate generation.
OpenAPI describes the full Pydantic response schema. Request bodies forbid extra fields, including
attempts to override a saved prompt. Keep the existing `/runs` and human review frontend contracts.

## Local demonstration and setup

From `backend`, in a normal Python 3.12 environment with `pip install -e '.[dev]'`:

```powershell
$env:DATABASE_URL='sqlite+pysqlite:///:memory:'
python -m pytest tests/test_prototype3.py -v
python -m uvicorn app.prototype3.routes:create_app --factory --port 8001
```

The tests demonstrate strong/weak/reference-grounded judgments, injection separation, malformed
outputs, reserved identity, duplicate prevention, partial results, critical gating, persistence
failure and API workflows using only mocked providers and fake storage. The factory exposes
`http://localhost:8001/docs` and returns 503 until injected, rather than pretending data is durable.
For a connected local app, construct `ReservedExecutor(omar_adapter, generation_provider,
Judge(separate_judge_provider), LinaAdapter())`, assign it to `app.state.reserved_executor`,
or pass it to `create_app(executor)`. Providers use `generate(prompt, model, temperature,
system_prompt=...)` and return `Generated`, including refusal and finish state. Keep credentials
in server-side configuration. Do not run a live provider as part of automated tests.

## Readiness and remaining dependencies

Ready for review: isolated judge transport, reused validation/arithmetic, reserved executor,
provisional API, mocked tests. No claim that branches are merge-clean: the current worktree
predates integrated Prototype 2. Reconcile imports when reviewing against the integration branch.
Blocked external integrations: Omar's production reservation/update helpers and state mapping,
Lina's canonical integrated registry in this worktree, agreed criticality/custom-scale extensions,
and Ahmad's adoption of the agreed saved-execution endpoints. PostgreSQL integration and live
provider behavior were not exercised. Existing Prototype 2 modules and uncommitted work were
not transplanted or replaced.

## Validation results (November 5, 2026)

| Check | Result |
| --- | --- |
| Current backend: `python -m pytest -q` | **108 passed, 0 failed** (45 new Prototype 3 cases; 63 existing cases). One installed Starlette/httpx deprecation warning. |
| Backend `ruff check` | Passed, zero violations. |
| Backend `ruff format --check` | Passed, 25 files already formatted. |
| Current frontend `npm run build` | Passed, TypeScript and Vite production build. No frontend test/lint scripts are declared in this worktree. |
| Preserved `.integration/prototype-2-assistant/backend` suite | **472 passed, 49 failed**, 11 warnings. The failures reach persistence requiring a prepared PostgreSQL schema; the in-memory SQLite test URL has no required tables. This separate snapshot is unchanged and this is not a successful PostgreSQL regression run. |

No paid calls were made. The installed Python packages were reused from `.venv/Lib/site-packages`
via `PYTHONPATH` (this workspace's `.venv` has no Python executable). Tests ran from the respective
backend directories with `DATABASE_URL=sqlite+pysqlite:///:memory:`. Disabled pytest plugin
autoload for the completed runs. Windows asyncio's socketpair stalled inside the sandbox;
the successful API test run required approved execution outside that sandbox. Abandoned stalled
test processes were stopped. No production database was connected or modified.

### Change inventory

- Modified `backend/app/main.py`: import and mount the isolated router, retaining prior edits.
- Added `backend/app/prototype3/__init__.py`: isolated package.
- Added `backend/app/prototype3/models.py`: internal request, saved snapshot and result schemas.
- Added `backend/app/prototype3/judge.py`: dedicated judge prompt, provider transport and validation adapter.
- Added `backend/app/prototype3/lina_rubric.py`: unchanged Lina validator source snapshot.
- Added `backend/app/prototype3/lina_points.py`: unchanged Lina point arithmetic source snapshot.
- Added `backend/app/prototype3/storage.py`: injected storage protocol and claim conflict.
- Added `backend/app/prototype3/executor.py`: reserved execution and canonical registry adapter.
- Added `backend/app/prototype3/routes.py`: provisional routes and injectable app factory.
- Added `backend/tests/test_prototype3.py`: 45 mocked cases including provider transport.
- Added this handoff. The initial-status audit record remains local and is not published.

All other files shown by `git status` were already modified/untracked before this task.

## Publication review

Prepared an isolated `pranjal` worktree from `72099027fcfbc39df5bc2000797a89a9fe658ffd`,
leaving the original dirty `main` worktree unchanged. At preparation time, neither a local
`pranjal` branch nor `origin/pranjal` existed. The branch contains only the eight package source
files, the Prototype 3 tests, this handoff, the two Prototype 3 additions to `main.py`, and the
required `httpx` runtime-dependency change in `backend/pyproject.toml` (12 files total).
The unrelated assistant import/route edits in the original `main.py` are excluded.

The separate publication tree passes **46 tests, 0 failures** (45 Prototype 3 cases plus the
foundation health test). Ruff lint and format checks pass (16 backend Python files), and
importing its real `app.main` confirms the Prototype 3 paths appear in OpenAPI. The earlier
108-test result belongs to the original working tree, including unrelated assistant work;
it is not the test count for the isolated commit. `httpx` was promoted from a dev dependency
to a runtime dependency because importing the mounted judge requires it in production.
No unrelated settings, assistant code, frontend edits, archives, environments, credentials,
caches, or local audit scripts/reports are included.

### Detailed review of the 49 preserved-snapshot failures

Reproduced **472 passed, 49 failed** against the unchanged Prototype 2 snapshot with SQLite
in memory. An SQLAlchemy engine `handle_error` listener associated database errors with each
pytest node. **All 49 failing cases encountered `no such table`**, including the HTTP 500
assertions whose routes sanitize the underlying exception. The sanitized, per-test audit is
retained locally in `.integration/prototype3-p2-failure-audit.json`; it is not published.

| Preserved test module | Failures |
| --- | ---: |
| `test_demo_integration.py` | 2 |
| `test_frontend_integration.py` | 6 |
| `test_prototype_history.py` | 2 |
| `test_registry_expansion.py` | 36 |
| `test_run_persistence.py` | 1 |
| `test_system_prompts.py` | 2 |
| **Total** | **49** |

None of these 49 observed failures demonstrates a Prototype 3 regression: they run in the
unchanged, separate snapshot, which does not import this new package, and each reached absent
database tables. This does not prove that no later assertion would fail once PostgreSQL is
available. The PostgreSQL-specific JSONB/identity schema cannot be verified by pointing the
suite at an empty SQLite database. A migrated PostgreSQL test database remains necessary
before claiming full persistence/integration validation; no production schema was changed.

No merge-blocking defect was found in the independently tested publication scope. Shared
integration remains blocked on Omar's real reservation/update adapter, Lina's canonical registry
imports in the target integration tree, and agreement on provisional APIs and critical policy.
The branch is ready for code integration review, not an assertion of end-to-end deployment readiness.
