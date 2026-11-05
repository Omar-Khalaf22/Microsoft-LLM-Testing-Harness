param([switch]$TestDatabase)
$ErrorActionPreference = 'Stop'
$P3Root = Split-Path -Parent $PSScriptRoot
$env:LLM_ENV_FILE = Join-Path $P3Root '.env.prototype3'
if (-not (Test-Path -LiteralPath $env:LLM_ENV_FILE)) { throw 'Create .env.prototype3 first.' }
# Reject inherited settings instead of silently connecting to a P2/shared database.
$P3Database = if ($TestDatabase) { 'llm_harness_p3_test' } else { 'llm_harness_p3_review' }
$P3Url = "postgresql+psycopg://llm_harness:local-p3-review-only@127.0.0.1:55433/$P3Database"
if ($env:DATABASE_URL -and $env:DATABASE_URL -ne $P3Url) {
    throw 'Inherited DATABASE_URL differs. Inspect it, then Remove-Item Env:DATABASE_URL and retry.'
}
$env:DATABASE_URL = $P3Url
$env:APP_ENV = 'development'
$env:AUTH_MODE = 'development'
$env:DEV_SUBJECT = 'omar-local'
$env:PROJECT_ID = 'prototype'
