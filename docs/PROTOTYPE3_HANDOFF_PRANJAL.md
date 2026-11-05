# Internal storage handoff — Pranjal

You own HTTP DTOs, routes, OpenAPI, profile management, preview calls, suite scheduling,
and progress transport. This package defines internal storage behavior; it does not
require the historical p3.1 HTTP proposal or an API version bump.

## Records and transaction ownership

All storage functions below accept a caller-owned SQLAlchemy `Session` and
`AccessContext`; they flush but do not commit. The coordinator must commit each
short reservation/claim/checkpoint/finalization transaction before making network calls.
Use `SessionLocal.begin()` in separate blocks, as in `app.storage.demo`.

```python
from app.storage.access import Principal, AccessContext, get_access
from app.storage.records import SavedDefinition, TestReference, ProfileSelection
from app.storage.definitions import (
    create_test, create_test_version, get_test_version, list_tests, list_test_versions,
    create_suite, revise_suite, get_suite, list_suites,
)
from app.storage.executions import (
    reserve_attempts, retrieve_execution, get_attempt, request_for_attempt,
    claim_attempt, heartbeat_attempt, save_target_response, finalize_attempt,
    recover_expired_attempt, create_rerun_plan, save_preview, get_preview,
)
from app.storage.executor_adapter import ReservedResultRepository
```

| Function | Inputs after `(session, access, ...)` | Return |
|---|---|---|
| create_test | `definition: SavedDefinition` | `TestVersion` |
| create_test_version | `test_id, definition, *, expected_version` | new immutable `TestVersion` |
| get_test_version | `ref: TestReference` | exact accessible version |
| list_test_versions | `test_id, *, after_version=0, limit=20` | immutable versions ordered by version number |
| list_tests/list_suites | `*, after="", limit=20` | ID-ordered ORM records, limit 1–100 |
| create_suite | `name, items: list[TestReference]` | `SuiteRevision` |
| revise_suite | `suite_id, name, items, *, expected_revision` | new immutable revision |
| get_suite | `suite_id, revision` | `(SuiteRevision, ordered SuiteItem list)` |
| reserve_attempts | `profiles, *, test=None, suite_id=None, suite_revision=None, idempotency_key=None, previews=None, rerun_of_run_id=None` | execution/progress/attempt dict |
| retrieve_execution | `execution_id` | same progress/attempt dict |
| get_attempt | `run_id` | scoped `TestRun` |
| claim_attempt | `run_id, *, lease_seconds=120` | opaque lease token |
| heartbeat_attempt | `run_id, token, *, lease_seconds=120` | None |
| save_target_response | `run_id, token, *, content, actual_model, latency_ms, usage` | None |
| finalize_attempt | `run_id, token, result: TestResult` | persisted `TestResult` |
| recover_expired_attempt | `run_id` | None; marks expired running row failed/interrupted |
| create_rerun_plan | `run_id, *, profile=None, test=None, idempotency_key=None, resolve_profile=None` | new reservation dict |
| save_preview | `test, profile, *, status, actual_model=None, interpretation=None, error_category=None` | immutable `Preview` |
| get_preview | `preview_id` | scoped `Preview` |

Storage errors (`app.storage.errors`) are `NotFound`, `Conflict`, and `AccessDenied`.
Validation errors derive from ValueError/Pydantic validation. Invalid persisted SQL
invariants raise IntegrityError. Roll back the whole transaction on any error.
Suggested transport mappings are 404/409/403/422; you choose your HTTP contracts.

## Save and approve

```python
definition = SavedDefinition(
    name="JSON count", objective="Produce machine readable data",
    prompt="Return JSON with count 3", state="draft",
    criteria=[{"criterion_id": "valid_json", "parameters": {}, "weight": 100}],
)
with SessionLocal.begin() as session:
    draft = create_test(session, access, definition)
with SessionLocal.begin() as session:
    approved = create_test_version(
        session, access, draft.test_id,
        definition.model_copy(update={"state": "approved"}), expected_version=1,
    )
```

Approval creates version **2**; version 1 stays draft. Identity and approval time
are recorded by the server. Effective instructions/defaults, criterion definitions,
catalog revision, and canonical hash are captured at save time. Prompt strings keep
their original whitespace. Legacy and selected criterion modes are exclusive.
Selected positive maxima sum to 100.00. Legacy zeros retain their earlier meaning.

## Trusted model selection

Construct `ProfileSelection` only from your server-managed resolver. Never bind it
directly to arbitrary HTTP bodies: callers must not supply their own parameter schema,
endpoint URLs, credentials, profile revision, or authorization context.

```python
profile = ProfileSelection(
    profile_id="target-a", profile_revision=3, provider="openai_compatible",
    endpoint_id="approved-eastus-deployment", requested_model="deployment-alias",
    parameter_schema={"type":"object", "properties":{
        "temperature":{"type":"number", "minimum":0, "maximum":2}},
        "additionalProperties":False},
    parameters={"temperature":0.2},
)
```

Omit unsupported temperature from both allowed schema and selected parameters.
The included executor adapter handles temperature only. Resolve additional provider
settings in your adapter before using them; it fails explicitly on extra parameters.
Revalidate profile availability at acceptance/rerun. A historical profile snapshot
does not prove its endpoint remains reachable or authorized today.
Default remote-profile reruns require `resolve_profile(archived_selection)` to return
the same validated selection, or an explicit validated override. Resolve from already
loaded trusted server configuration; do not make network calls while holding a storage
transaction. Local demo profiles can be resolved directly. Active attempts cannot be rerun.

## Reservation and execution lifecycle

```python
with SessionLocal.begin() as session:
    plan = reserve_attempts(session, access, [profile], test=TestReference(
        test_id=approved.test_id, test_version=approved.version),
        idempotency_key="client-request-identity")
# All pending rows and IDs now exist before provider invocation.
run_id = plan["attempts"][0]["run_id"]
with SessionLocal.begin() as session:
    token = claim_attempt(session, access, run_id)
    request = request_for_attempt(session, access, run_id)
repo = ReservedResultRepository(SessionLocal, access, run_id, token)
result = TestExecutor(target_provider, repo, judge_context=trusted_judge_context).execute(request)
```

`plan` has `execution_id`, `status`, progress counts (`pending/running/completed/failed`),
and attempts with `run_id`, pinned `test_id/test_version`, `suite_position`, and
`model_position`. Positions are item 1/model A, item 1/model B, item 2/model A/B.
This is deterministic storage order; serial dispatch remains your coordinator's job.

`TestRequest.reserved_run_id` and `frozen_system_prompt` are the minimal executor seam.
The existing provider/scoring dispatcher is reused. `ReservedResultRepository` saves
the target response in a committed transaction before evaluation, then updates the
reserved row through `finalize_attempt`. Do not call insert-only `save_run_result`
or `PostgresResultRepository.save` for a reserved ID. Those remain the P2 inline
compatibility path and may create versions only when saving the finished inline run.

Provider failures finalize failed evidence. Unexpected crashes retain pending/running
records; an expired running lease can be marked interrupted. Recovery never sends
another remote request. Explicit rerun creates new IDs and links to the original.
Never reclaim a still-live lease. Leases are 30–900 seconds; heartbeat during long
multi-criterion evaluation before expiry. The adapter itself does not run a heartbeat
thread. Default lease is 120 seconds, so your coordinator must extend it for longer work.
Database clock and guarded tokens prevent stale finalization. Parent locks are always
taken before child locks; there are no database locks across model calls.

Successful children remain intact if another attempt fails. Parent progress indicates
failure if any terminal child failed. There is no suite score or suite pass/fail.
Zero is a valid completed numerical result; missing/failed evaluator totals remain null.

## Preview and judge roles

Save previews with the exact test reference and trusted selected profile. Completed
interpretation requires purpose, deliverable, constraints, and success_conditions.
Technical errors use timeout/provider_unavailable/invalid_response categories.
Reservation `previews` keys are `"suite_position:model_position"`, for example:

```json
{"1:1":{"preview_id":"preview_...","acknowledge_error":true}}
```

The shared canonical hash includes exact task/objective/instructions/rubric/profile
revision/settings. Wrong-resource, stale, and wrong-model previews conflict.
Technical failures require explicit acknowledgment or a retry. Previews are optional,
unscored diagnostics, and never enter the scored model's conversation context.

Supply `judge_context` containing judge_provider, judge_model, judge_profile_id, and
judge_profile_revision. Recommendation assistant, target, judge, and human identity
remain separate. Provider-reported model identity and usage are stored separately
from configured aliases/profile revision; unknown provider metadata remains unknown.
Legacy latency means target plus evaluation; new target/evaluation metrics are
additional fields. Do not relabel old durations.

## Auth, reviews, history and transfer surfaces

Use `get_access` as a FastAPI dependency. It supplies a verified/authorized server
context. Legacy ownership stays unknown, within the configured prototype workspace.
The explicit policy is shared access for all authorized subjects in that workspace;
it is not per-user ownership isolation. Browser login/refresh remains your integration.

Lina's review table and routes are reused. Incoming reviewer_id is accepted for
old clients but ignored for identity; server subject wins. Ahmad's form now displays
that subject. Reviews append revisions under a run lock and never change automated
scores. Imported attribution is preserved separately from the authenticated importer.

| Existing/new surface | Storage mapping |
|---|---|
| POST /runs | existing inline service/executor/PostgresResultRepository compatibility |
| GET /runs | existing bare-array full-result compatibility, scoped |
| GET /runs/{id} | existing relational detail reader, reserved/null-state support |
| GET /history/runs | `app.storage.history.list_history_summaries` |
| POST/GET /runs/{id}/reviews | Lina repository + server access context |
| POST /evidence/export | `export_evidence(session, access, run_ids)` |
| POST /evidence/import | `import_evidence(session, access, EvidenceBundle)` |
| GET /auth/me | server subject/project integration adapter |
| GET /health, /ready | process liveness; DB/schema/auth readiness |

Schema 4.0 and CLI/browser transfer are Omar-owned. Strict run ID conflicts abort
the entire import. Surrogate test-version/review row IDs are local; source review
IDs/importer/source hash live in attribution. No automatic copy mode is implemented.
Unsupported historical evaluator methods remain viewable but cannot be rerun as if
they were supported. There are 38 supported registry criteria; completeness remains
planned. Direct helper support for completeness does not make it executable by API.

## Migration order and pending integration

0001 → 0002_week5 → 0003_version_names → 0004_prototype2 →
0005_lina_reviews → **0006_omar_storage**. One head. Earlier published migrations
are unchanged. P3 downgrade uses backup restoration instead of deleting evidence.

Pending with you: test/suite/execution/preview/model-profile HTTP contracts and routes,
coordinator scheduling/heartbeats/recovery policy, live profile verification, approved
endpoints, real OIDC/browser registration and token acquisition, and early local-model
connectivity from the intended Azure network. Ahmad owns those remaining feature
screens. Lina owns live judge discrimination validation. See requirements/status and
deployment operations docs for exact external inputs and verification limitations.
