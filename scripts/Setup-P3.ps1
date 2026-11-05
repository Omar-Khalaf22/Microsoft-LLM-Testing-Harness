$ErrorActionPreference = 'Stop'
$P3Root = Split-Path -Parent $PSScriptRoot
Set-Location $P3Root
if (-not (Test-Path -LiteralPath '.env.prototype3')) {
    Copy-Item -LiteralPath '.env.prototype3.example' -Destination '.env.prototype3'
}
. (Join-Path $PSScriptRoot 'Use-P3Environment.ps1')
docker compose -f docker-compose.prototype3.yml up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'P3 database did not become ready.' }
$P3Exists = docker compose -f docker-compose.prototype3.yml exec -T postgres psql -U llm_harness -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='llm_harness_p3_test'"
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect test database.' }
if (($P3Exists -join '').Trim() -ne '1') {
    docker compose -f docker-compose.prototype3.yml exec -T postgres createdb -U llm_harness llm_harness_p3_test
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated test database.' }
}
Push-Location backend
try {
    & "$P3Root\.venv\Scripts\python.exe" -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'P3 app migrations failed.' }
} finally { Pop-Location }
