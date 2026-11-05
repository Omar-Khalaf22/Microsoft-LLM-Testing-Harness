# Apply and run Omar's Prototype 3 package

The ZIP contains `files/` (complete Omar source files), `omar-prototype3.patch`,
`BASE.json`, `changed-file-manifest.json`, `deleted-files.txt`, `VERIFICATION.json`,
`Stage-OmarChanges.ps1`, and this guide. Apply the patch once; the overlay is provided
for inspection/copyability and must not be copied again over an already patched tree.

## 1. Extract outside your repository

Save the ZIP to Downloads, then use a new extraction directory:

```powershell
$P3Zip = Join-Path $env:USERPROFILE 'Downloads\Omar_Prototype3_Package.zip'
$P3Package = Join-Path $env:USERPROFILE 'Downloads\Omar_Prototype3_Package'
if (Test-Path -LiteralPath $P3Package) { throw 'Choose a fresh extraction folder; preserve existing files' }
Expand-Archive -LiteralPath $P3Zip -DestinationPath $P3Package
Get-Content (Join-Path $P3Package 'BASE.json')
```

If using the generated desktop artifact directly, replace `$P3Zip` with its actual
local path. The ZIP layout is flat at its root, with source files under `files/`.

## 2. Prepare the exact teammate baseline before applying Omar's patch

For a new destination only:

```powershell
Set-Location 'C:\USF\Senior Project\Codebase'
if (Test-Path -LiteralPath '.\Microsoft-LLM-Testing-Harness-P3') {
    throw 'Inspect the existing checkout/worktree; do not overwrite it'
}
git clone --branch omar-prototype2-integration https://github.com/Omar-Khalaf22/Microsoft-LLM-Testing-Harness.git Microsoft-LLM-Testing-Harness-P3
if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
Set-Location '.\Microsoft-LLM-Testing-Harness-P3'
git switch -c omar-prototype3-storage-integration 5964466eb6e9e36266f5e85bc29ba6f00373e4ca
if ($LASTEXITCODE -ne 0) { throw 'Branch setup failed; inspect existing branches' }
git merge --no-ff 5d8196a6783be8b8e216e96fa64fe22708d6d864 -m 'Merge Lina P3 baseline'
if ($LASTEXITCODE -ne 0) { throw 'Resolve the Lina integration before proceeding' }
git merge --no-ff 4af4aa60a76b9a90ad6c0dc47345eab5fdc6ca12 -m 'Merge Ahmad P3 baseline'
if ($LASTEXITCODE -ne 0) { throw 'Resolve the Ahmad integration before proceeding' }
$P3Tree = (git rev-parse 'HEAD^{tree}').Trim()
if ($P3Tree -ne '54cccdd151acab0387631f023893cba1bcf1a7fb') { throw 'Integrated baseline tree differs; stop and diagnose' }
if (git status --porcelain) { throw 'The integrated baseline must be clean before patch application' }
code .
```

Git may require your existing user.name/user.email to create local merge commits.
Use your normal identity. Merge commit SHAs/timestamps can differ from generation;
the integrated **tree** must match. Do not substitute current main, newer branch heads,
or a P2-only checkout. Keep Pranjal's later integration as a separate reviewed step.

## 3. Check and apply exactly once

In the same PowerShell terminal, with `$P3Package` still set:

```powershell
$P3Patch = Join-Path $P3Package 'omar-prototype3.patch'
git apply --check $P3Patch
if ($LASTEXITCODE -ne 0) { throw 'Patch check failed. Resolve the baseline/path mismatch before continuing' }
git apply $P3Patch
if ($LASTEXITCODE -ne 0) { throw 'Patch failed. Inspect the repository before continuing' }
git diff --check
git status --short
```

If the patch check fails, stop. Do not force, partially apply, reset unrelated work,
or copy random replacements over mismatched files. Compare BASE, tree, file changes
and whether the patch was already applied.

## 4. Install, configure and migrate

Python 3.12, Node 22, Git, and Docker Desktop/Linux containers are prerequisites.

```powershell
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -c backend/constraints.prototype3.txt -e 'backend[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Backend install failed' }
Push-Location frontend
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed' }
Pop-Location
if (-not (Test-Path -LiteralPath '.env.prototype3')) {
    Copy-Item -LiteralPath '.env.prototype3.example' -Destination '.env.prototype3'
}
Set-ExecutionPolicy -Scope Process Bypass
& '.\scripts\Setup-P3.ps1'
```

The private environment is ignored. Edit keys locally; never commit them or paste
them into chat. Setup rejects inherited database settings that could select P2/shared
data. See `docs/PROTOTYPE3_LOCAL_SETUP.md` for the explicit guard and troubleshooting.

## 5. Start in separate terminals

Terminal A, repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
. '.\scripts\Use-P3Environment.ps1'
Push-Location backend
& '..\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1 --no-access-log
```

Terminal B:

```powershell
Set-Location 'C:\USF\Senior Project\Codebase\Microsoft-LLM-Testing-Harness-P3\frontend'
npm.cmd run dev
```

Open http://127.0.0.1:5174. Check API http://127.0.0.1:8001/ready.
PostgreSQL uses 127.0.0.1:55433. The P2 port/volume remain separate.

Terminal C, repository root, for direct storage acceptance:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
. '.\scripts\Use-P3Environment.ps1'
Push-Location backend
& '..\.venv\Scripts\python.exe' -m app.storage.demo
Pop-Location
```

## 6. Test and inspect

Use a fresh terminal or inspect/remove the previous process DATABASE_URL before
switching from the app database to the separate test database:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
& '.\scripts\Test-P3.ps1'
Push-Location frontend
npm.cmd run build
Pop-Location
git diff --check
git diff --stat
git status --short
```

Optional browser tests, with API/Vite running and Playwright Chromium installed:

```powershell
Push-Location frontend
$env:HARNESS_UI_URL = 'http://127.0.0.1:5174'
# Or point PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH to an installed Edge/Chrome executable.
npm.cmd run test:e2e
npm.cmd run test:e2e:p3
Pop-Location
```

Review `docs/PROTOTYPE3_HANDOFF_PRANJAL.md`, requirements/status and verification.
The local demo does not prove live models or team completion. Azure and production
identity instructions are in operations docs and remain separate operator actions.

## 7. Stage only the delivered allowlist, review, commit and push yourself

From the consumer repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& (Join-Path $P3Package 'Stage-OmarChanges.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Staging failed; inspect before continuing' }
git diff --cached --check
git diff --cached --stat
git diff --cached
# After your review and tests:
git commit -m 'Implement Prototype 3 storage and deployment preparation'
if ($LASTEXITCODE -ne 0) { throw 'Commit failed' }
git push -u origin omar-prototype3-storage-integration
```

The staging helper contains explicit delivered paths and checks the intended branch.
It does not stage private `.env.prototype3`, caches, dependencies, dumps or unrelated
files. Generation did not commit your VS Code checkout or push this branch. These
commands are for you to run after applying/reviewing the package. No remote publishing
or paid Azure deployment was performed by the generation task.
