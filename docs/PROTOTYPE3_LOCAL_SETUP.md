# Prototype 3 local setup (Windows PowerShell)

Apply Omar's package to the exact integrated baseline first. See the package's
`APPLY_AND_RUN.md` and `BASE.json`. Never copy the overlay onto an arbitrary P2 checkout.
The separate generation checkout does not commit changes in your VS Code checkout.

## Prerequisites and install

Install Python 3.12, Node 22, Git, and Docker Desktop with Linux containers running.
The generation verification used Python 3.12.14, local Node 24.16.0, and Node 22
in the multi-stage container build. Python 3.12.10 is compatible with the package.

In Terminal 1, after applying the patch:

```powershell
Set-Location 'C:\USF\Senior Project\Codebase\Microsoft-LLM-Testing-Harness-P3'
py -3.12 --version
node --version
docker version
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -c backend/constraints.prototype3.txt -e 'backend[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed' }
Push-Location frontend
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed' }
Pop-Location
if (-not (Test-Path -LiteralPath '.env.prototype3')) {
    Copy-Item -LiteralPath '.env.prototype3.example' -Destination '.env.prototype3'
}
Set-ExecutionPolicy -Scope Process Bypass
& '.\scripts\Setup-P3.ps1'
```

`Setup-P3.ps1` starts PostgreSQL 16, creates the test database only if absent,
sets `LLM_ENV_FILE` to the absolute private P3 file, selects the app database,
and applies Alembic from `backend`, where `script_location = alembic` resolves.
It never runs `down -v`, drops an app database, or overwrites a private environment file.

The settings loader gives inherited process variables priority over the env file.
The scripts reject a mismatched inherited `DATABASE_URL`. Inspect its destination
privately, remove that process variable, then retry in the intended terminal:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
& '.\scripts\Setup-P3.ps1'
```

Do not paste connection strings or provider keys into chat. Edit the ignored private
`.env.prototype3` locally. The supplied password is exclusively for local loopback use.

## Start the API and browser

Terminal 1:

```powershell
Set-Location 'C:\USF\Senior Project\Codebase\Microsoft-LLM-Testing-Harness-P3'
Set-ExecutionPolicy -Scope Process Bypass
. '.\scripts\Use-P3Environment.ps1'
Push-Location backend
& '..\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1 --no-access-log
```

Terminal 2:

```powershell
Set-Location 'C:\USF\Senior Project\Codebase\Microsoft-LLM-Testing-Harness-P3\frontend'
npm.cmd run dev
```

Open http://127.0.0.1:5174. Vite requires port 5174 and proxies same-origin API
requests to 127.0.0.1:8001. The bundled build uses same-origin URLs as well.
`VITE_API_BASE_URL` is an optional build-time override; normally leave it absent.

Terminal 3:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8001/health'
Invoke-RestMethod 'http://127.0.0.1:8001/ready'
Invoke-RestMethod 'http://127.0.0.1:8001/auth/me'
```

Expected: `status=ok`, `status=ready/schema=0006_omar_storage`, and the configured
server development identity `omar-local` in workspace `prototype`.

## Verify the storage handoff and tests

In a fresh terminal at the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
. '.\scripts\Use-P3Environment.ps1'
Push-Location backend
& '..\.venv\Scripts\python.exe' -m app.storage.demo
Pop-Location
```

This saves an approved version, reserves/commits IDs, claims one attempt, runs the
explicit deterministic demo provider, checkpoints its response, and finalizes the
same ID. It is a real PostgreSQL example, not evidence of live model connectivity.
The new run is available in browser history. Test/suite management screens and the
HTTP coordinator remain teammate work; this command exercises their storage seam.

For all tests, start a fresh terminal or inspect/remove the prior app `DATABASE_URL`:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
& '.\scripts\Test-P3.ps1'
Push-Location frontend
npm.cmd run build
Pop-Location
```

Tests use `llm_harness_p3_test`, not the app database. They create temporary named
schemas for fresh/P2 migration and transfer checks, then remove only those schemas.
Randomly named evidence from concurrency tests can remain in the dedicated test DB.

History benchmark (100 seeded runs, 100 HTTP first-page requests, model time excluded):

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
. '.\scripts\Use-P3Environment.ps1' -TestDatabase
Push-Location backend
& '..\.venv\Scripts\python.exe' -m app.storage.benchmark
Pop-Location
```

The benchmark refuses any database name other than `llm_harness_p3_test`. Its local
measurement does not verify the DDD Azure p95 target. Read the delivered verification
report for measured values and the storage metric's definition.

## Evidence transfer

Open a completed run, choose **Export opened run**, and save the JSON. Exports include
the complete parent execution and rerun-source closure. Running executions must finish
or be recovered before transfer. **Import evidence JSON** validates schema 4.0 and
rejects existing run IDs with HTTP 409. Import into a separate empty deployment to
test restoration without collisions. There is no implicit overwrite or copy mode.

CLI alternative, from `backend` with the app environment selected:

```powershell
& '..\.venv\Scripts\python.exe' -m app.storage.cli export 'C:\path\new-evidence.json' --run-id 'RUN_ID_FROM_HISTORY'
& '..\.venv\Scripts\python.exe' -m app.storage.cli import 'C:\path\evidence-from-another-instance.json'
```

CLI export refuses to replace an existing file. Shared-mode CLI authentication uses
`HARNESS_ACCESS_TOKEN` from the private process environment and verifies it normally.

## Live model and shared identity configuration

The default provider is explicitly `demo`. To opt into a bounded live test, configure
an approved server endpoint, key, and `LLM_PROVIDER=openai` in the private environment,
restart the API, and use one small prompt. Set `JUDGE_MODEL`, `JUDGE_PROFILE_ID`, and
`JUDGE_PROFILE_REVISION` separately from `ASSISTANT_MODEL`. An unconfigured judge
produces an unavailable total while preserving the target response.

Pranjal must supply the real profile resolver, allowed settings, profile/endpoint
identities and revisions, two live target configurations, and local-model connectivity.
The reserved executor adapter currently supports `temperature`; unsupported extra
provider parameters fail explicitly until his provider adapter handles them.
An omitted temperature is omitted from the OpenAI-compatible request, allowing
profiles whose model does not support that parameter.

Shared deployment uses `APP_ENV=production`, `AUTH_MODE=oidc`, an HTTPS JWKS URL,
issuer/audience, and explicit authorized subjects. JWT signatures, issuer, audience,
expiry, and subject membership are checked. The workspace comes from server config.
`setAccessToken()` in `frontend/src/api.ts` is the browser-login integration point;
Pranjal still needs to implement token acquisition/refresh. There is no completed
shared browser-login flow in this package. Development identity cannot authorize
requests in shared mode.

## Stop, restart, backup, restore

Ctrl+C stops API/Vite. Stop PostgreSQL with:

```powershell
docker compose -f docker-compose.prototype3.yml stop
docker compose -f docker-compose.prototype3.yml up -d --wait
```

The named volume `llm-harness-p3-review_p3-postgres` persists. P2 continues to use
55432; P3 uses only 127.0.0.1:55433 and its own volume/project.

Byte-safe PowerShell backup (do not redirect a binary pg_dump to a host file):

```powershell
$P3Backup = Join-Path (Get-Location) ('p3-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump')
docker compose -f docker-compose.prototype3.yml exec -T postgres pg_dump -U llm_harness -Fc -f /tmp/p3-backup.dump llm_harness_p3_review
if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
docker cp 'llm-harness-p3-review-postgres-1:/tmp/p3-backup.dump' $P3Backup
if ($LASTEXITCODE -ne 0) { throw 'Backup copy failed' }
```

Keep backups private and outside Git. Restore into a **new**, named database,
never over the app or P2 database:

```powershell
docker compose -f docker-compose.prototype3.yml exec -T postgres createdb -U llm_harness llm_harness_p3_restore
if ($LASTEXITCODE -ne 0) { throw 'Choose a fresh restore database; do not overwrite it' }
docker cp $P3Backup 'llm-harness-p3-review-postgres-1:/tmp/p3-restore.dump'
if ($LASTEXITCODE -ne 0) { throw 'Restore copy failed' }
docker compose -f docker-compose.prototype3.yml exec -T postgres pg_restore -U llm_harness --exit-on-error --no-owner -d llm_harness_p3_restore /tmp/p3-restore.dump
if ($LASTEXITCODE -ne 0) { throw 'Restore failed; inspect the separate restore database' }
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Wrong Python or missing packages | Use `.venv\Scripts\python.exe`, and confirm Python 3.12. |
| Alembic cannot find scripts | Run from `backend`, not the root. |
| DATABASE_URL guard fails | Inspect inherited destination privately; remove that process variable and reselect the intended P3 environment. |
| Docker permission/daemon error | Start Docker Desktop; confirm Linux containers and local user access. |
| Port already occupied | Inspect owning process; do not stop P2. Defaults are P3 55433/8001/5174. |
| Browser API/CORS errors | Prefer Vite's same-origin proxy. Remove an old VITE_API_BASE_URL override, restart Vite, and inspect `/ready`. |
| HTTP 503 auth | Explicitly configure development identity locally or real OIDC in shared mode. |
| HTTP 401/403 shared | Verify issuer/audience/expiry, signature key, subject allowlist, and browser token adapter. |
| Rubric total unavailable | Check nonempty reference evidence and explicit judge configuration; no failed-evaluator zero is substituted. |
| Import 409 | A source identity already exists or conflicts; use a fresh target and inspect the bundle. |
| Patch check fails | Stop. Compare baseline tree/SHAs and working changes; do not force application. |
