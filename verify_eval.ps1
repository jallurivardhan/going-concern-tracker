#!/usr/bin/env pwsh
# verify_eval.ps1 — Smoke test for the accuracy benchmark
#
# Runs `python -m gct.cli.eval --json`, parses the output, and asserts:
#   1. precision >= 0.95
#   2. recall >= 0.50  (low threshold OK: v1.0 covers auditor's-report only,
#                       not management MD&A disclosures)
#   3. Zero cases without a DB match
#   4. Both critical cases (Tupperware, BBBY) match expected severity
#
# Usage:
#   cd apps/api
#   & ..\..\verify_eval.ps1
#
# Prerequisite: DATABASE_URL in environment or .env

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$API_DIR = Join-Path $PSScriptRoot "apps\api"
Push-Location $API_DIR

Write-Host ""
Write-Host "=== EVAL SMOKE TEST ===" -ForegroundColor Cyan
Write-Host "Working directory: $API_DIR"
Write-Host ""

# ── Run benchmark ─────────────────────────────────────────────────────────────
Write-Host "Running accuracy benchmark..." -ForegroundColor Yellow
$rawJson = python -m gct.cli.eval --json 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: benchmark CLI exited with code $LASTEXITCODE" -ForegroundColor Red
    Write-Host $rawJson
    Pop-Location
    exit 1
}

# Strip any Rich-generated noise lines before the JSON (benchmark may emit
# non-JSON text on stderr even with --json; capture only the JSON block)
$jsonStart = ($rawJson | Select-String -Pattern '^\{' -List).LineNumber
if ($null -eq $jsonStart) {
    Write-Host "ERROR: no JSON found in benchmark output" -ForegroundColor Red
    Write-Host $rawJson
    Pop-Location
    exit 1
}
$jsonLines = $rawJson[($jsonStart - 1)..($rawJson.Count - 1)]
$report = $jsonLines -join "`n" | ConvertFrom-Json

$fails = @()

# ── Assertion 1: precision >= 0.95 ───────────────────────────────────────────
$precision = [double]$report.precision
if ($precision -lt 0.95) {
    $fails += "FAIL: precision=$precision < 0.95"
} else {
    Write-Host "  [PASS] precision=$precision >= 0.95" -ForegroundColor Green
}

# ── Assertion 2: recall >= 0.50 ──────────────────────────────────────────────
$recall = [double]$report.recall
if ($recall -lt 0.50) {
    $fails += "FAIL: recall=$recall < 0.50"
} else {
    Write-Host "  [PASS] recall=$recall >= 0.50" -ForegroundColor Green
}

# ── Assertion 3: zero missing DB cases ───────────────────────────────────────
$missing = [int]$report.cases_without_db_match
if ($missing -gt 0) {
    $fails += "FAIL: $missing case(s) have no DB match"
} else {
    Write-Host "  [PASS] cases_without_db_match=$missing" -ForegroundColor Green
}

# ── Assertion 4a: Tupperware FY2022 is critical ───────────────────────────────
$tupperware = $report.case_results | Where-Object { $_.case_id -like "tupperware_fy2022*" }
if ($null -eq $tupperware) {
    $fails += "FAIL: Tupperware FY2022 case not found in results"
} elseif ($tupperware.actual_severity -ne "critical") {
    $fails += "FAIL: Tupperware FY2022 actual_severity='$($tupperware.actual_severity)' expected 'critical'"
} elseif (-not $tupperware.matches_expected) {
    $fails += "FAIL: Tupperware FY2022 does not match expected label"
} else {
    Write-Host "  [PASS] Tupperware FY2022 severity=critical, matches_expected=true" -ForegroundColor Green
}

# ── Assertion 4b: BBBY original FY2022 is critical ───────────────────────────
$bbby = $report.case_results | Where-Object { $_.case_id -like "bbby_original_fy2022*" }
if ($null -eq $bbby) {
    $fails += "FAIL: BBBY original FY2022 case not found in results"
} elseif ($bbby.actual_severity -ne "critical") {
    $fails += "FAIL: BBBY original FY2022 actual_severity='$($bbby.actual_severity)' expected 'critical'"
} elseif (-not $bbby.matches_expected) {
    $fails += "FAIL: BBBY original FY2022 does not match expected label"
} else {
    Write-Host "  [PASS] BBBY original FY2022 severity=critical, matches_expected=true" -ForegroundColor Green
}

# ── Assertion 4c: WeWork FY2022 is none (canonical edge case) ────────────────
$wework = $report.case_results | Where-Object { $_.case_id -like "wework_fy2022*" }
if ($null -eq $wework) {
    $fails += "FAIL: WeWork FY2022 case not found in results"
} elseif ($wework.actual_severity -ne "none") {
    $fails += "FAIL: WeWork FY2022 actual_severity='$($wework.actual_severity)' expected 'none' (EY issued clean opinion; GC in MD&A only)"
} else {
    Write-Host "  [PASS] WeWork FY2022 severity=none (correct: EY issued clean opinion)" -ForegroundColor Green
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Benchmark summary:" -ForegroundColor Cyan
Write-Host "  total_cases:           $($report.total_cases)"
Write-Host "  cases_with_db_match:   $($report.cases_with_db_match)"
Write-Host "  precision:             $($report.precision)"
Write-Host "  recall:                $($report.recall)"
Write-Host "  f1:                    $($report.f1)"
Write-Host "  accuracy:              $($report.accuracy)"
Write-Host "  true_positives:        $($report.true_positives)"
Write-Host "  true_negatives:        $($report.true_negatives)"
Write-Host "  false_positives:       $($report.false_positives)"
Write-Host "  false_negatives:       $($report.false_negatives)"
Write-Host ""

if ($fails.Count -gt 0) {
    Write-Host "=== RESULT: FAIL ===" -ForegroundColor Red
    foreach ($f in $fails) {
        Write-Host "  $f" -ForegroundColor Red
    }
    Pop-Location
    exit 1
} else {
    Write-Host "=== RESULT: PASS ===" -ForegroundColor Green
    Write-Host "All eval assertions passed." -ForegroundColor Green
    Pop-Location
    exit 0
}
