$ErrorActionPreference = 'Stop'
$P3Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'Use-P3Environment.ps1') -TestDatabase
Push-Location (Join-Path $P3Root 'backend')
try {
    & "$P3Root\.venv\Scripts\python.exe" -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Test migrations failed.' }
    & "$P3Root\.venv\Scripts\python.exe" -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed.' }
    & "$P3Root\.venv\Scripts\python.exe" -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Format failed.' }
    & "$P3Root\.venv\Scripts\python.exe" -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
} finally { Pop-Location }
