# Windows / VS Code review steps

Use this package instead of the earlier ZIPs. It includes the complete modified
and new files plus one patch against Lina's exact snapshot. No commit or push is
part of these steps. Run commands one at a time and stop at the first error.

## 1. Start from the combined branch

Your known starting point is `omar-prototype2-structured` at `d7e7859`, with only
an untracked `prototype2-structured.patch`. That downloaded patch can stay.

In your existing VS Code PowerShell terminal:

```powershell
Set-Location "C:\USF\Senior Project\Codebase\Microsoft-LLM-Testing-Harness"
git status --short
git fetch origin prototype-2-lina
if ($LASTEXITCODE -ne 0) { throw "Fetch failed. Stop here." }
git switch --no-track -c omar-prototype2-integration e9fafc01d6323e6c934a928552735428bf614557
if ($LASTEXITCODE -ne 0) { throw "Branch creation failed. Stop here." }
git log -1 --oneline
```

Expect `e9fafc0`. This creates a new local branch; your existing Omar branch stays
available. The package already includes your structured evaluators, so do not
cherry-pick or apply an older patch on top.

## 2. Apply the reviewed package

Extract the ZIP outside the repository, for example into:

`C:\USF\Senior Project\prototype2-integration`

Open `REVIEW.md` and the `files` folder in VS Code to inspect the exact source.
`files` mirrors the repository paths. `manifest.json` lists every new/modified
file and its SHA-256. The patch contains exactly those source changes.

From the repository root:

```powershell
$p2Package = "C:\USF\Senior Project\prototype2-integration"
git apply --check "$p2Package\prototype2-integration.patch"
if ($LASTEXITCODE -ne 0) { throw "Patch does not match. Stop and review the error." }
git apply "$p2Package\prototype2-integration.patch"
if ($LASTEXITCODE -ne 0) { throw "Patch application failed. Stop here." }
git status --short
git diff --check
code docs/prototype2-integration.md
```

The changes remain unstaged. Review changed and new files in VS Code's Source
Control panel. The patch changes `.env.example`; it does not overwrite your
actual `.env` or introduce an API key.

## 3. Start isolated PostgreSQL 16 and install backend dependencies

Start Docker Desktop. The review database uses loopback port 55432 and its own
named volume. It does not modify your existing application database.

```powershell
docker compose -p llm-harness-p2-review -f docker-compose.prototype2.yml up -d --wait
```

Keep your existing Python 3.12 `.venv` active. In this terminal, save the original
settings before pointing the backend at the review database:

```powershell
$p2PreviousDatabaseUrl = $env:DATABASE_URL
$p2PreviousProvider = $env:LLM_PROVIDER
$env:DATABASE_URL = "postgresql+psycopg://llm_harness:local-p2-review-only@127.0.0.1:55432/llm_harness_p2_review"
$env:LLM_PROVIDER = "demo"
Set-Location .\backend
python -m pip install -e ".[dev]"
python -m alembic upgrade head
```

Expect migration head `0004_prototype2`. Keep tests on this isolated database;
they create synthetic records. Do not run them against a database with important
application data. The named review volume preserves evidence across app and
container restarts.

## 4. Run the checks on native PostgreSQL

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

The complete suite includes a concurrent-version-creation test. The accompanying
verification report distinguishes tests already executed here from native
PostgreSQL 16 and live-provider checks still needed on your machine.

## 5. Run the browser workflow

In the backend terminal, keep the review environment values above and start:

```powershell
python -m uvicorn app.main:app --reload
```

In a second VS Code terminal:

```powershell
Set-Location "C:\USF\Senior Project\Codebase\Microsoft-LLM-Testing-Harness\frontend"
npm ci
npm run build
npm run dev
```

Use Node 22.12+ and open http://localhost:5173.

Try this complete review:

1. Enter a test name, a JSON-focused objective and a prompt such as
   `Return JSON with count equal to 3.`
2. Set the model to `demo-json-v1`. Configure base and additional system
   instructions under **System instructions**.
3. Generate criteria. In demo mode the UI explicitly labels these deterministic
   suggestions; no external model call occurs.
4. Include/remove/add criteria, edit their parameter JSON and point allocations,
   and make the total 100.00. The parameters editor shows each criterion's schema.
5. Approve the configuration and choose **Run and save test**.
6. Inspect numerical scores, maxima, evidence, unavailable token counts and saved
   original suggestions versus approved criteria. There is no overall quality
   classification.
7. Reload the browser, reopen the saved run, and use **Back to Test**. Your
   system instructions and selected configuration should be restored.
8. Rerun unchanged settings: same version, new run. Change a system prompt or
   criterion: new version, earlier records unchanged.
9. Use **Original six-check configuration** to confirm the old workflow remains
   usable. Zero disables a legacy check; new selected allocations must be positive.

Optional reproducible browser test, with both servers running in demo mode:

```powershell
npx playwright install chromium
npm run test:e2e
```

## 6. Live provider check after reviewing demo mode

In the backend terminal, stop Uvicorn before changing environment values.
Use your own OpenAI-compatible key locally and set `LLM_PROVIDER=openai`.
`OPENAI_BASE_URL` is server configuration. `ASSISTANT_MODEL=gpt-4o-mini` is the
fixed recommendation model, separate from the model entered in the form.
Do not share the key in chat or place it in a source file. Live calls consume
provider credits. There are no automatic paid retries.

Generate one recommendation, review it, run one approved test, and reopen the
saved record to check model compatibility and actual usage reporting. Missing
counts must stay unavailable. Mocked transport tests do not establish real model
quality or provider compatibility.

## 7. End the local review

Stop the frontend/backend servers with Ctrl+C. From the original backend
PowerShell terminal, restore the environment values you saved:

```powershell
Set-Location "C:\USF\Senior Project\Codebase\Microsoft-LLM-Testing-Harness"
docker compose -p llm-harness-p2-review -f docker-compose.prototype2.yml down
$env:DATABASE_URL = $p2PreviousDatabaseUrl
$env:LLM_PROVIDER = $p2PreviousProvider
```

`down` preserves the review volume. No reset, clean, merge, commit or push is
performed by this package. When the review is complete, decide separately which
changes to commit and push.
