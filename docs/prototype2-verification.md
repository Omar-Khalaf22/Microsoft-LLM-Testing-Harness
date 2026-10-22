# Prototype 2 verification evidence

Verification applies to the local source package based on Lina's `e9fafc0` and
Pranjal's included `2492c38`. No GitHub CI run or remote push was created for this
package. The earlier branches' green CI does not validate these new changes.

## Completed checks

| Check | Evidence |
| --- | --- |
| Backend checks | 362 passed; one concurrent-version test deliberately excluded in the embedded SQL environment |
| SQL migration | Alembic revisions 0001 through 0004 applied successfully to PostgreSQL-derived PGlite via the PostgreSQL wire protocol |
| SQL integration | Saved selected IDs/parameters/weights, generated and approved snapshots, prompt and rubric version changes, old-version reuse, rollback, unavailable usage, provider/evaluator failure evidence and exact fresh-client retrieval |
| Restart coverage | Existing prompt-persistence test starts a separate Python writer process, exits it, and retrieves its committed evidence in a fresh process |
| Scoring | 33.33 + 33.33 + 33.34 full credit is 100.00; a 0.06 maximum never earns 0.1; half-cent rounding is consistent; invalid allocations are rejected |
| Evaluators | Existing 157 structured cases plus content, pattern/numeric and dispatcher coverage |
| Assistant | Mocked live transport verifies fixed model, separate instructions, registry input, full rejection of invalid suggestions, failures and approval provenance; no real API credits used |
| Static checks | Ruff lint, Ruff formatting and Git whitespace checks passed |
| Frontend | TypeScript compilation and Vite production build passed |
| Browser | Headless Chromium ran the React UI against FastAPI and embedded SQL: objective → suggestions → remove/add/edit → approve → execute → save → reload → reopen → unchanged rerun → new version after prompt edit |
| Responsive review | Desktop and 390-pixel mobile results inspected; no browser page errors in the tested flow |

Browser automation uses a real browser engine and actual local HTTP/SQL calls.
The only generated test responses in that flow come from the clearly labeled demo
provider. The live-provider unit tests mock HTTP transport; no real model-quality
or service-compatibility claim follows from those tests.

## Required local follow-up

Native PostgreSQL 16 could not run in this environment. PGlite serializes work
through an embedded engine, so it cannot establish the real server's concurrent
locking behavior. Run the complete suite against the provided PostgreSQL 16
Compose service. It includes:

`test_concurrent_instruction_edits_get_distinct_sequential_versions`

The expected complete suite is 363 tests. Treat its actual native result as the
authority; the local report above has one explicit exclusion.

A real OpenAI-compatible recommendation and scored run with a configured API key
also remain unverified. The review guide includes that final smoke check. No
manual-source changes or publishing are necessary to run the demo workflow.

## Scope of the evidence

These checks establish the tested Prototype 2 flow, not full SRS certification.
They do not measure final Azure deployment, security/access controls, workload
percentiles, accessibility conformance, semantic-judge reliability or human-rating
features. Those are separate final-system work streams.

The design follows the DDD's numeric-only results, 100.00-point validation,
incomplete-total rule, immutable history and unavailable-metadata policy. The
SRS's preview-blocking assumption is superseded by Omar's DDD-first decision.
