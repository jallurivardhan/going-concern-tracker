#!/usr/bin/env pwsh
# verify_frontend.ps1 — Verify the frontend compiles, tests pass, and builds correctly.

$ErrorActionPreference = "Continue"
$PASS = 0
$FAIL = 0

function Write-Step($msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Write-Pass($msg) {
    Write-Host "  [PASS] $msg" -ForegroundColor Green
    $script:PASS++
}

function Write-Fail($msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
    $script:FAIL++
}

# ── 1. Check .env.local ───────────────────────────────────────────────────────
Write-Step "Checking apps/web/.env.local"
$envPath = "apps/web/.env.local"
if (Test-Path $envPath) {
    $content = Get-Content $envPath -Raw
    if ($content -match "NEXT_PUBLIC_API_BASE_URL") {
        Write-Pass ".env.local exists and contains NEXT_PUBLIC_API_BASE_URL"
    } else {
        Write-Fail ".env.local exists but NEXT_PUBLIC_API_BASE_URL is missing"
    }
} else {
    Write-Fail ".env.local not found at $envPath"
}

# ── 2. Type-check ─────────────────────────────────────────────────────────────
Write-Step "Running type-check (tsc --noEmit)"
Push-Location apps/web
npm run type-check 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Pass "TypeScript type-check passed"
} else {
    Write-Fail "TypeScript type-check failed (exit code $LASTEXITCODE)"
}
Pop-Location

# ── 3. Lint ───────────────────────────────────────────────────────────────────
Write-Step "Running ESLint"
Push-Location apps/web
npm run lint 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Pass "ESLint passed"
} else {
    Write-Fail "ESLint failed (exit code $LASTEXITCODE)"
}
Pop-Location

# ── 4. Tests ──────────────────────────────────────────────────────────────────
Write-Step "Running frontend tests (vitest)"
Push-Location apps/web
npm test 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Pass "Frontend tests passed"
} else {
    Write-Fail "Frontend tests failed (exit code $LASTEXITCODE)"
}
Pop-Location

# ── 5. Build ──────────────────────────────────────────────────────────────────
Write-Step "Building Next.js app"
Push-Location apps/web
npm run build 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Pass "Next.js build succeeded"
} else {
    Write-Fail "Next.js build failed (exit code $LASTEXITCODE)"
}
Pop-Location

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host "`n========================================" -ForegroundColor White
Write-Host "  FRONTEND VERIFICATION SUMMARY" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White
Write-Host "  Passed: $PASS" -ForegroundColor Green
Write-Host "  Failed: $FAIL" -ForegroundColor $(if ($FAIL -gt 0) { "Red" } else { "Green" })
Write-Host "========================================" -ForegroundColor White

if ($FAIL -gt 0) {
    Write-Host "`nOne or more checks failed. See output above." -ForegroundColor Red
    exit 1
} else {
    Write-Host "`nAll checks passed." -ForegroundColor Green
    exit 0
}
