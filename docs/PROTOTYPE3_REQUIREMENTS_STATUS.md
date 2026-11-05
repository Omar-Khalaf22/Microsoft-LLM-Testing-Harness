# Requirement and acceptance status

This maps the supplied prompt's requirements, not invented SRS IDs. Referenced DDD
pages are taken from the prompt; the source PDF/briefing were not available. The P2
code and pinned teammate implementations are the implementation baseline.

| Requirement | Status / evidence |
|---|---|
| Save tests before execution; immutable versions; objective/prompt/instructions; default capture; server approval/hash | Implemented; PostgreSQL save/retrieve/approval/concurrent-version tests and direct demo. |
| Ordered suites with exact versions, contiguous positions, repeated item distinction, revision conflicts | Implemented; transaction helpers, deferred SQL constraint, snapshot/revision tests. |
| Commit all attempt IDs before provider calls | Implemented; observer-provider test reads committed running row/version in another session. |
| Claims, ownership tokens, heartbeats, expired recovery, no silent duplicate call | Implemented; concurrent claims/live-lease/recovery tests. Coordinator scheduling/heartbeat policy remains Pranjal-owned. |
| Target checkpoint before judge; stable reserved-ID finalization | Implemented; reserved adapter and judge-failure test verifies response exists before judge invocation. |
| Preserve failed/incomplete evidence and successful children; progress | Implemented; lifecycle/progress services and tests. No suite total/pass-fail is introduced. |
| Execution idempotency scoped to workspace/actor/request identity | Implemented; advisory transaction lock and concurrent same/conflicting-key tests. |
| Original/rerun relationships and empty new reviews | Implemented; storage plan/test. Historical profiles require explicit executable saved version/profile when unknown. Live resolver availability remains external. |
| NUMERIC maxima, total 100.00, score bounds and criterion version membership | Implemented; database constraints, transactional validation, negative SQL/import tests. Old unknown maxima/ratios remain null. |
| Preview persistence and shared hash; stale/wrong-model/resource rejection; technical-error continuation | Implemented storage support and tests. Diagnostic provider calls/HTTP transport remain Pranjal-owned. |
| Separate assistant/target/judge/human roles; reported identity/metrics | Implemented seams and persistence; judge alias/reporting test. Live role/profile validation remains external. |
| Factual/grounding prerequisites; completeness support count | Nonempty reference evidence required. Exactly 38 registry criteria supported; completeness remains planned despite direct-helper tests. |
| Human review history, concurrency, server identity, score independence | Lina table reused, append-only revisions and PostgreSQL endpoint/concurrency tests; Ahmad form updated. |
| Summary-first scoped keyset history; detail retrieval; legacy array | Implemented; SQL summary projection, pagination/scope tests, UI load-more and comparison detail fetch. |
| Schema 4.0 export/import, strict conflicts/atomicity, preserved evidence | Implemented API/CLI/browser controls and separate-schema PostgreSQL round-trip. Optional copy mode deliberately omitted. |
| Unsupported historical evaluators remain viewable | Import does not require registry support; new execution revalidates support. |
| Fresh/P2 migration without changed historical meaning; one head | Implemented; fresh schema and populated-P2 migration tests. Earlier published migrations unchanged. |
| Explicit development identity; verified JWT/shared fail-closed behavior | Implemented; signature/issuer/audience/expiry/subject/production-development rejection tests. Live issuer/browser login remains externally unverified. |
| Approved server endpoint support and safe rendering/logging | Server-controlled endpoint selection, shared HTTPS allowlist, text rendering and sanitized operation boundary. Pranjal supplies production profile resolver/credentials. |
| Liveness and database/schema readiness | Implemented `/health` and `/ready`; local process/container checks. |
| Isolated Windows local setup, app/test DBs, correct ports/env guard | Delivered scripts/docs; exact setup/install/run verification recorded separately. |
| Combined frontend/backend behavior | Combined backend tests and frontend/container build; browser evidence in verification report. |
| Docker, Bicep, controlled migration job, secret injection/private DB | Implemented; local container build/Bicep compile. No actual Azure provisioning/deployment performed. |
| Backup/recovery and cost assumptions | Concrete byte-safe local procedures plus Azure operations guidance. Regional prices, recovery policy and actual Azure restore remain externally unverified. |
| History performance/storage measurements | Reproducible 100-run/100-request local benchmark; actual numbers in verification report. DDD Azure p95 target remains unverified. |
| Transferable Omar-only package against integrated teammate baseline | ZIP, patch, full-file overlay, BASE, manifest, apply-check and final-tree verification produced by packaging step. |

## External inputs and remaining owners

- **Pranjal:** HTTP contracts/routes for saved tests/suites/executions/model profiles/
  previews/reruns, real coordinator dispatch/heartbeat/recovery integration, approved
  server profiles/settings/endpoints, browser OIDC login/refresh, two live models and
  early local-model connectivity from Azure.
- **Ahmad:** test/suite selection and progress, preview, profile selection, and rerun
  screens. Existing comparison/review/theme remain integrated; Omar added only history,
  transfer and identity adapters.
- **Lina:** live model-judge discrimination with the genuinely different strong/weak/
  misleading answer fixtures and a small approved budget. Deterministic fake judge
  tests prove handling, not model discrimination. Completeness remains planned.
- **Omar/operator/sponsor:** approved subscription/tenant/group/region/resource choices,
  permissions, production issuer/audience/subject policy, approved provider secrets,
  private endpoint/local-model access, recovery/retention decisions, and regional cost
  validation. These block shared/live verification, not the delivered local code.

Newer remote work observed: `lina-prompt-understanding` at
`ec6a2afa61c4fa3a062f0fcf39717460072dc59c` contains additional preview UI/API work.
It was inspected but not merged into the requested reproducible pinned baseline.
Pranjal heads were unchanged at `ec7242f...` and `2492c381...` and contain no described
P3 coordinator. Integrate newer branches deliberately against these storage interfaces.
