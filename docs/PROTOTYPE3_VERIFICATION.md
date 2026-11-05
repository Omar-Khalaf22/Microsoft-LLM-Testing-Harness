# Generation verification

The authoritative packaging results are also recorded in the ZIP's `VERIFICATION.json`.
This report distinguishes actual local results from external work that was not performed.

## Sources

- Repository: https://github.com/Omar-Khalaf22/Microsoft-LLM-Testing-Harness
- P2: `5964466eb6e9e36266f5e85bc29ba6f00373e4ca`
- Lina merged first: `5d8196a6783be8b8e216e96fa64fe22708d6d864`
- Ahmad merged second: `4af4aa60a76b9a90ad6c0dc47345eab5fdc6ca12`
- Generation baseline commit: `c338dcda63aed82997cffd5759a8a7d3ef5c3728`
- Integrated base tree: `54cccdd151acab0387631f023893cba1bcf1a7fb`
- Intended consumer branch: `omar-prototype3-storage-integration`

The repository was freshly cloned into the isolated generation workspace. Those
reviewed heads and P2 were unchanged remotely. Pranjal heads remained `ec7242f...`
and `2492c381...`; no described P3 coordinator was present. Lina's newer preview
branch `ec6a2afa...` was inspected but excluded from the pinned integration.
No applicable AGENTS.md was found. The original VS Code checkout was not modified.

## Actual local checks

| Check | Evidence |
|---|---|
| Python install | Fresh root `.venv`, Python 3.12.14, exact editable install with delivered constraints. |
| PostgreSQL | Real PostgreSQL 16 in the isolated P3 container, separate app/test databases, loopback 55433. |
| Backend | 504 tests passed after added mixed-outcome, preview-context and rerun-resolution coverage; see final package report for final applied-checkout results. |
| Migration | Fresh installation and populated P2→P3 upgrade in independent PostgreSQL schemas, original values compared before/after, one Alembic head. |
| Storage concurrency | Version conflicts, idempotent reservation, claims, ownership/recovery and review revision tests. |
| Transfer | Schema 4.0 validation, strict conflicts, snapshot/membership/score checks, separate-schema actual export/import round trip, original evidence retained. |
| Auth | Real RSA signing tests for JWT signature/issuer/audience/expiry/subject failures and server workspace selection; shared development identity rejected. |
| Lint/format | Ruff check and format check; schema regeneration/check; diff whitespace check. |
| Frontend | TypeScript and Vite production build on local Node 24.16.0; Node 22 build in the container. |
| P2 browser | Headless Edge: suggest→edit/reject/add→approve→execute→save→reload→rerun→version change. |
| P3 browser | Summary pagination/load more, detail retrieval, server reviewer identity, review revisions, safe text rendering, export, strict-import conflict, and comparison. Screenshot inspected and transfer-panel height corrected. |
| Local consumer commands | Delivered Setup-P3.ps1 executed successfully; storage demo saved/reserved/claimed/checkpointed/finalized a real DB run. |
| Backup/recovery | Binary dump written inside container, copied byte-safely, restored into a fresh separate database; run counts matched (48 at that check). |
| Container | Multi-stage frontend/API image built; final image smoke/readiness checks recorded in package report. |
| Azure templates | Official Bicep CLI 0.48.1 compiles main.bicep and app.bicep; no Azure provisioning performed. |
| PowerShell | Scripts parsed without syntax errors; local setup executed, deployment script compiled/inspected only. |
| Package | Omar-only patch checked/applied to a fresh integrated-baseline clone; index tree and every full-source overlay blob compared. Exact evidence in `VERIFICATION.json`. |

## History measurement

`python -m app.storage.benchmark` used 100 synthetic seeded runs and 100 HTTP requests
through FastAPI TestClient, excluding model invocation. The observed local p95 was
**62.78 ms**, mean **25.67 ms**, first-page response **7,644 bytes**.

Seed prompt+response+configuration UTF-8 bytes totaled **6,205,500**. The measured
database size at that time was **10,658,319 bytes**, including indexes, system/storage
overhead and other tests. These are explicit metrics, not a claimed 100 KiB/run real
workload. This is local Windows/Docker evidence; the DDD agreed-Azure p95 target is
**not verified**. Re-run in the agreed Azure environment with its actual identity,
network, SKU and workload before accepting that target.

## Limitations

No live/paid model calls, real OIDC-provider/browser login, private local-model
connectivity, Azure subscription deployment/what-if, regional price/availability
validation, or Azure backup/restore was performed. CI source is updated but was not
pushed or run remotely. Deterministic providers prove persistence/error handling and
fake judge validation, not production model discrimination. The source DDD PDF and
briefing were unavailable; their references came from the supplied prompt.

Existing pytest warnings concern class collection names, Alembic configuration
deprecation, and the installed Starlette/httpx TestClient deprecation. They do not
represent skipped tests. No tests were deleted or weakened to pass.
