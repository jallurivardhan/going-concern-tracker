#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Smoke-tests the Tier-2 classification layer end-to-end.
.DESCRIPTION
    1. Verifies required environment variables are present.
    2. Classifies exactly one AAPL auditor report (--limit 1 --force).
    3. Queries the database to confirm the GoingConcernFlag row was written.
    4. Reports cost estimate and prints PASS / FAIL summary.
    5. (Post-Prompt-4) Shows expected severity breakdown for all companies
       once the three going-concern CIKs have been ingested.

Expected controls (always severity=none):
    AAPL  x4   MSFT  x5   PTON  x5   BYND  x5   BYON  x5

Expected going-concern positives (after --ciks ingest):
    Bed Bath & Beyond Inc. (CIK 0000886158) -- critical/elevated, 2022-2023 10-Ks
    WeWork Inc.            (CIK 0001813756) -- critical/elevated, 2022-2023 10-Ks
    Tupperware Brands      (CIK 0001008654) -- critical/elevated, 2022-2024 10-Ks

.EXAMPLE
    .\verify_classifier.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$passCount = 0
$failCount = 0

function Write-Pass([string]$msg) {
    Write-Host "  [PASS] $msg" -ForegroundColor Green
    $script:passCount++
}
function Write-Fail([string]$msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
    $script:failCount++
}

Write-Host ""
Write-Host "=== Going Concern Tracker -- Classifier Smoke Test ===" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------
# Step 1: Environment variables
# ------------------------------------------------------------------
Write-Host "[ 1/4 ] Checking environment variables..."

$envFile = Join-Path $PSScriptRoot ".env"
$envContent = ""
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
}

foreach ($varName in @("ANTHROPIC_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")) {
    $val = [System.Environment]::GetEnvironmentVariable($varName)
    if (-not $val -and $envContent -match "(?m)^$varName=(.+)$") {
        $val = $Matches[1].Trim('"').Trim("'")
    }
    if ($val) {
        Write-Pass "$varName is set"
    } else {
        Write-Fail "$varName is NOT set -- add it to .env or your environment"
    }
}

if ($script:failCount -gt 0) {
    Write-Host ""
    Write-Host "Environment checks failed. Fix the above before continuing." -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------
# Step 2: Run classifier smoke test
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[ 2/4 ] Running smoke-test classification (AAPL, --limit 1)..."
Write-Host "        Expected: severity=none, cost<`$0.01" -ForegroundColor DarkGray
Write-Host ""

$prevDir = Get-Location
Set-Location (Join-Path $PSScriptRoot "apps\api")

$classifyOutput = ""
$classifyExitCode = 0
try {
    $classifyOutput = python -m gct.cli.classify --tickers AAPL --limit 1 --force 2>&1
    $classifyExitCode = $LASTEXITCODE
} catch {
    $classifyExitCode = 1
    $classifyOutput = $_.Exception.Message
}

Set-Location $prevDir

Write-Host $classifyOutput

if ($classifyExitCode -eq 0) {
    Write-Pass "classify command exited successfully"
} else {
    Write-Fail "classify command exited with code $classifyExitCode"
}

# ------------------------------------------------------------------
# Step 3: Verify DB row
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[ 3/4 ] Querying database for AAPL GoingConcernFlag rows..."

Set-Location (Join-Path $PSScriptRoot "apps\api")

$tmpPy = Join-Path $env:TEMP "gct_db_check.py"
@"
from sqlalchemy import text
from gct.database import SessionLocal

db = SessionLocal()
try:
    rows = db.execute(text(
        "SELECT f.accession_number, f.filing_date, gcf.severity, gcf.classification_confidence "
        "FROM going_concern_flags gcf "
        "JOIN filings f ON f.id = gcf.filing_id "
        "JOIN companies c ON c.id = gcf.company_id "
        "WHERE c.ticker = 'AAPL' "
        "ORDER BY f.filing_date DESC LIMIT 3"
    )).fetchall()
    if rows:
        for r in rows:
            print(f"  {r.accession_number}  {r.filing_date}  severity={r.severity}  conf={float(r.classification_confidence):.2f}")
        print("OK")
    else:
        print("NO_ROWS")
finally:
    db.close()
"@ | Set-Content $tmpPy -Encoding UTF8

$dbResult = python $tmpPy 2>&1
Set-Location $prevDir

Write-Host $dbResult

if ($dbResult -match "OK") {
    Write-Pass "GoingConcernFlag row(s) found in database"
} elseif ($dbResult -match "NO_ROWS") {
    Write-Fail "No GoingConcernFlag rows for AAPL -- was the write committed?"
} else {
    Write-Fail "Unexpected database query result"
}

# ------------------------------------------------------------------
# Step 4: Cost check
# ------------------------------------------------------------------
Write-Host ""
Write-Host "[ 4/4 ] Checking cost estimate from classify output..."

$costMatch = [regex]::Match($classifyOutput, '\$(\d+\.\d+)')
if ($costMatch.Success) {
    $cost = [double]$costMatch.Groups[1].Value
    if ($cost -lt 0.01) {
        Write-Pass "Cost `$$cost is under `$0.01 (expected for one AAPL report)"
    } else {
        Write-Fail "Cost `$$cost exceeds `$0.01 -- review model selection"
    }
} else {
    Write-Host "  [WARN] Could not parse cost from output (may appear differently in Rich output)" -ForegroundColor Yellow
}

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PASS: $script:passCount    FAIL: $script:failCount"
if ($script:failCount -eq 0) {
    Write-Host "  SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Next steps to ingest real going-concern companies:" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Step A -- Ingest three going-concern companies by CIK:" -ForegroundColor DarkGray
    Write-Host "      cd apps/api" -ForegroundColor DarkGray
    Write-Host "      python -m gct.cli.backfill --ciks 0000886158,0001813756,0001008654 --max-10k 5 --max-10q 0" -ForegroundColor DarkGray
    Write-Host "      #   0000886158 = Bed Bath & Beyond Inc. (bankrupt Apr 2023)" -ForegroundColor DarkGray
    Write-Host "      #   0001813756 = WeWork Inc. (bankrupt Nov 2023)" -ForegroundColor DarkGray
    Write-Host "      #   0001008654 = Tupperware Brands Corporation (going-concern 2022-2024)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Step B -- Re-parse auditor reports (idempotent):" -ForegroundColor DarkGray
    Write-Host "      python -m gct.cli.reparse_auditor_reports" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Step C -- Classify all reports (auto-skips already-classified):" -ForegroundColor DarkGray
    Write-Host "      python -m gct.cli.classify" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Expected classification outcomes after Step C:" -ForegroundColor DarkGray
    Write-Host "      AAPL  x4  -> severity=none  (clean control)" -ForegroundColor DarkGray
    Write-Host "      MSFT  x5  -> severity=none  (clean control)" -ForegroundColor DarkGray
    Write-Host "      PTON  x5  -> severity=none or watch  (distressed, no formal opinion)" -ForegroundColor DarkGray
    Write-Host "      BYND  x5  -> severity=none or watch  (distressed, no formal opinion)" -ForegroundColor DarkGray
    Write-Host "      BYON  x5  -> severity=none  (Beyond, Inc. is healthy)" -ForegroundColor DarkGray
    Write-Host "      Bed Bath & Beyond  xN -> severity=critical or elevated (2022-2023 10-Ks)" -ForegroundColor DarkGray
    Write-Host "      WeWork             xN -> severity=critical or elevated (2022-2023 10-Ks)" -ForegroundColor DarkGray
    Write-Host "      Tupperware Brands  xN -> severity=critical or elevated (2022-2024 10-Ks)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Validate with this query (requires psql or a DB client):" -ForegroundColor DarkGray
    Write-Host "      SELECT c.name, c.ticker, gcf.severity, COUNT(*)" -ForegroundColor DarkGray
    Write-Host "      FROM going_concern_flags gcf" -ForegroundColor DarkGray
    Write-Host "      JOIN companies c ON c.id = gcf.company_id" -ForegroundColor DarkGray
    Write-Host "      GROUP BY c.name, c.ticker, gcf.severity ORDER BY c.name;" -ForegroundColor DarkGray
} else {
    Write-Host "  SMOKE TEST FAILED -- fix issues above before running full classify" -ForegroundColor Red
    exit 1
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
