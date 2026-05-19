#!/usr/bin/env pwsh
# verify_api.ps1 — Smoke test for the Going Concern Tracker REST API
#
# Starts the FastAPI server in the background, hits each endpoint, verifies
# expected data, then stops the server.
#
# Usage (from repo root):
#   cd apps/api
#   & ..\..\verify_api.ps1
#
# Prerequisites: DATABASE_URL must be set (in .env or environment).

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$API_DIR = Join-Path $PSScriptRoot "apps\api"
$BASE_URL = "http://localhost:8000"
$fails = @()
$passes = @()

function Pass([string]$msg) {
    $script:passes += $msg
    Write-Host "  [PASS] $msg" -ForegroundColor Green
}

function Fail([string]$msg) {
    $script:fails += $msg
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
}

function Invoke-Api([string]$path, [string]$method = "GET", [hashtable]$body = $null) {
    $uri = "$BASE_URL$path"
    $params = @{ Uri = $uri; Method = $method; UseBasicParsing = $true; TimeoutSec = 10 }
    if ($body) {
        $params.Body = ($body | ConvertTo-Json)
        $params.ContentType = "application/json"
    }
    return Invoke-WebRequest @params
}

Write-Host ""
Write-Host "=== GOING CONCERN TRACKER — API SMOKE TEST ===" -ForegroundColor Cyan
Write-Host "Working directory: $API_DIR"
Write-Host ""

# ── Start server ──────────────────────────────────────────────────────────────
Write-Host "Starting FastAPI server..." -ForegroundColor Yellow
Push-Location $API_DIR
$serverProcess = Start-Process python `
    -ArgumentList "-m", "uvicorn", "gct.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 4

try {
    # (server is already started above)
    # ── 1. Health check ───────────────────────────────────────────────────────
    try {
        $r = Invoke-Api "/api/health"
        if ($r.StatusCode -eq 200) { Pass "/api/health returns 200" }
        else { Fail "/api/health status=$($r.StatusCode)" }
    } catch { Fail "/api/health threw: $_" }

    # ── 2. OpenAPI docs ───────────────────────────────────────────────────────
    try {
        $r = Invoke-Api "/api/docs"
        if ($r.StatusCode -eq 200) { Pass "/api/docs renders (200)" }
        else { Fail "/api/docs status=$($r.StatusCode)" }
    } catch { Fail "/api/docs threw: $_" }

    # ── 3. Stats — 2 critical flags ───────────────────────────────────────────
    try {
        $r = Invoke-Api "/api/stats"
        $stats = $r.Content | ConvertFrom-Json
        if ($stats.total_flags_active -ge 2) {
            Pass "/api/stats total_flags_active=$($stats.total_flags_active) >= 2"
        } else {
            Fail "/api/stats total_flags_active=$($stats.total_flags_active) < 2"
        }
        if ($stats.flag_breakdown.critical -ge 2) {
            Pass "/api/stats flag_breakdown.critical=$($stats.flag_breakdown.critical) >= 2"
        } else {
            Fail "/api/stats flag_breakdown.critical=$($stats.flag_breakdown.critical) < 2"
        }
        if ($stats.total_companies_tracked -ge 8) {
            Pass "/api/stats total_companies_tracked=$($stats.total_companies_tracked) >= 8"
        } else {
            Fail "/api/stats total_companies_tracked=$($stats.total_companies_tracked) < 8"
        }
    } catch { Fail "/api/stats threw: $_" }

    # ── 4. Flags — at least 2 items (the two critical flags) ─────────────────
    try {
        $r = Invoke-Api "/api/flags"
        $flags = $r.Content | ConvertFrom-Json
        if ($flags.items.Count -ge 2) {
            Pass "/api/flags default returns $($flags.items.Count) items >= 2"
        } else {
            Fail "/api/flags default returned $($flags.items.Count) items < 2"
        }
        # Verify each item has citation fields
        foreach ($item in $flags.items) {
            if (-not $item.quoted_language) { Fail "Flag missing quoted_language: $($item.id)" }
            if (-not $item.filing) { Fail "Flag missing filing: $($item.id)" }
        }
        if ($flags.items.Count -ge 2) {
            Pass "/api/flags items contain quoted_language and filing"
        }
    } catch { Fail "/api/flags threw: $_" }

    # ── 5. Flag detail with report_excerpt ────────────────────────────────────
    try {
        $r = Invoke-Api "/api/flags"
        $firstFlagId = ($r.Content | ConvertFrom-Json).items[0].id
        $r2 = Invoke-Api "/api/flags/$firstFlagId"
        $detail = $r2.Content | ConvertFrom-Json
        if ($r2.StatusCode -eq 200) { Pass "/api/flags/{id} returns 200" }
        if ($null -ne $detail.report_excerpt -or $null -ne $detail.report_total_length) {
            Pass "/api/flags/{id} has report_excerpt or report_total_length"
        } else {
            Fail "/api/flags/{id} missing report_excerpt"
        }
    } catch { Fail "/api/flags/{id} threw: $_" }

    # ── 6. Flag 404 ───────────────────────────────────────────────────────────
    try {
        $r = Invoke-WebRequest -Uri "$BASE_URL/api/flags/00000000-0000-0000-0000-000000000000" `
            -Method GET -UseBasicParsing -TimeoutSec 10 -ErrorAction SilentlyContinue
        if ($r.StatusCode -eq 404) { Pass "/api/flags/{unknown_id} returns 404" }
        else { Fail "/api/flags/{unknown_id} returned $($r.StatusCode) not 404" }
    } catch {
        # Invoke-WebRequest throws on 4xx when not SilentlyContinue... check message
        if ($_.Exception.Response.StatusCode.value__ -eq 404) {
            Pass "/api/flags/{unknown_id} returns 404"
        } else {
            Fail "/api/flags/{unknown_id} threw: $_"
        }
    }

    # ── 7. Companies — >= 8 ──────────────────────────────────────────────────
    try {
        $r = Invoke-Api "/api/companies"
        $companies = $r.Content | ConvertFrom-Json
        if ($companies.items.Count -ge 8) {
            Pass "/api/companies returns $($companies.items.Count) items >= 8"
        } else {
            Fail "/api/companies returned $($companies.items.Count) items < 8"
        }
    } catch { Fail "/api/companies threw: $_" }

    # ── 8. Company detail ─────────────────────────────────────────────────────
    try {
        $r = Invoke-Api "/api/companies/0001008654"
        $company = $r.Content | ConvertFrom-Json
        if ($r.StatusCode -eq 200 -and $company.cik -eq "0001008654") {
            Pass "/api/companies/0001008654 returns Tupperware"
        } else {
            Fail "/api/companies/0001008654 wrong response"
        }
    } catch { Fail "/api/companies/0001008654 threw: $_" }

    # ── 9. Company 404 ────────────────────────────────────────────────────────
    try {
        $r = Invoke-WebRequest -Uri "$BASE_URL/api/companies/0000000000" `
            -Method GET -UseBasicParsing -TimeoutSec 10 -ErrorAction SilentlyContinue
        if ($r.StatusCode -eq 404) { Pass "/api/companies/{unknown} returns 404" }
        else { Fail "/api/companies/{unknown} returned $($r.StatusCode)" }
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 404) {
            Pass "/api/companies/{unknown} returns 404"
        } else {
            Fail "/api/companies/{unknown} threw: $_"
        }
    }

    # ── 10. Company filings ───────────────────────────────────────────────────
    try {
        $r = Invoke-Api "/api/companies/0001008654/filings"
        $filings = $r.Content | ConvertFrom-Json
        if ($filings.items.Count -ge 1) {
            Pass "/api/companies/{cik}/filings returns $($filings.items.Count) filings"
        } else {
            Fail "/api/companies/{cik}/filings returned 0 items"
        }
    } catch { Fail "/api/companies/{cik}/filings threw: $_" }

    # ── 11. Search — q=tupp finds Tupperware ─────────────────────────────────
    try {
        $r = Invoke-Api "/api/search?q=tupp"
        $search = $r.Content | ConvertFrom-Json
        if ($search.total_returned -ge 1 -and ($search.results | Where-Object { $_.name -like "*Tupperware*" })) {
            Pass "/api/search?q=tupp finds Tupperware"
        } else {
            Fail "/api/search?q=tupp returned: $($search | ConvertTo-Json -Compress)"
        }
    } catch { Fail "/api/search threw: $_" }

    # ── 12. Search — short q returns 422 ─────────────────────────────────────
    try {
        $r = Invoke-WebRequest -Uri "$BASE_URL/api/search?q=a" `
            -Method GET -UseBasicParsing -TimeoutSec 10 -ErrorAction SilentlyContinue
        if ($r.StatusCode -eq 422) { Pass "/api/search?q=a returns 422" }
        else { Fail "/api/search?q=a returned $($r.StatusCode)" }
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 422) {
            Pass "/api/search?q=a returns 422"
        } else {
            Fail "/api/search?q=a threw: $_"
        }
    }

    # ── 13. Methodology endpoint ──────────────────────────────────────────────
    try {
        $r = Invoke-Api "/api/methodology"
        $meth = $r.Content | ConvertFrom-Json
        if ($r.StatusCode -eq 200 -and $meth.methodology_version) {
            Pass "/api/methodology returns 200 with methodology_version"
        } else {
            Fail "/api/methodology missing data"
        }
        if ($meth.current_metrics) {
            Pass "/api/methodology current_metrics populated"
        } else {
            Write-Host "  [INFO] /api/methodology current_metrics is null (run eval first)" -ForegroundColor Yellow
        }
    } catch { Fail "/api/methodology threw: $_" }

    # ── 14. POST subscriptions ────────────────────────────────────────────────
    try {
        $testEmail = "verify_api_test_$(Get-Random)@example.com"
        $r = Invoke-Api "/api/subscriptions" "POST" @{ email = $testEmail }
        $sub = $r.Content | ConvertFrom-Json
        if ($r.StatusCode -eq 200 -and $sub.ok -and $sub.subscription_id) {
            Pass "/api/subscriptions POST creates row (id=$($sub.subscription_id))"
        } else {
            Fail "/api/subscriptions POST unexpected response: $($r.Content)"
        }
    } catch { Fail "/api/subscriptions POST threw: $_" }

} catch {
    Fail "Unexpected error: $_"
}

# ── Stop server ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Stopping server (PID $($serverProcess.Id))..." -ForegroundColor Yellow
Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
Pop-Location

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "Passed: $($passes.Count)" -ForegroundColor Green
Write-Host "Failed: $($fails.Count)" -ForegroundColor $(if ($fails.Count -gt 0) { "Red" } else { "Green" })
if ($fails.Count -gt 0) {
    foreach ($f in $fails) { Write-Host "  FAIL: $f" -ForegroundColor Red }
    Write-Host ""
    Write-Host "=== RESULT: FAIL ===" -ForegroundColor Red
    exit 1
} else {
    Write-Host ""
    Write-Host "=== RESULT: PASS ===" -ForegroundColor Green
    Write-Host "OpenAPI docs: $BASE_URL/api/docs" -ForegroundColor Cyan
    exit 0
}
