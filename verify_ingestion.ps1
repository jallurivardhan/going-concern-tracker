$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Name)
    Write-Host ""
    Write-Host "Running step: $Name" -ForegroundColor Cyan
}

function Write-Result {
    param([string]$Name, [bool]$Passed)
    $padded = $Name.PadRight(36)
    if ($Passed) {
        Write-Host "  $padded" -NoNewline
        Write-Host "PASS" -ForegroundColor Green
    } else {
        Write-Host "  $padded" -NoNewline
        Write-Host "FAIL" -ForegroundColor Red
    }
}

if (-not (Test-Path ".env")) {
    Write-Host ".env file not found at repo root" -ForegroundColor Red
    exit 1
}

Get-Content .env | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$results = [ordered]@{}

Write-Step "sec_email_configured"
$email = [Environment]::GetEnvironmentVariable("SEC_USER_AGENT_EMAIL", "Process")
if ($email -and $email -ne "") {
    Write-Host "  SEC_USER_AGENT_EMAIL is set"
    $results["sec_email_configured"] = $true
} else {
    Write-Host "  SEC_USER_AGENT_EMAIL is missing" -ForegroundColor Red
    $results["sec_email_configured"] = $false
}

Write-Step "small_ingestion"
Write-Host "  Running: python -m gct.cli.backfill --tickers AAPL --max-10k 1 --max-10q 0"
Push-Location apps/api
try {
    python -m gct.cli.backfill --tickers AAPL --max-10k 1 --max-10q 0
    $results["small_ingestion"] = ($LASTEXITCODE -eq 0)
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
    $results["small_ingestion"] = $false
} finally {
    Pop-Location
}

Write-Step "company_row_exists"
Push-Location apps/api
try {
    $script1 = "from gct.database import SessionLocal`nfrom gct.models import Company`nfrom sqlalchemy import select`nwith SessionLocal() as s:`n    row = s.execute(select(Company).where(Company.ticker == 'AAPL')).scalar_one_or_none()`n    print('FOUND' if row else 'MISSING')"
    $check1 = python -c $script1
    Write-Host "  $check1"
    $results["company_row_exists"] = ($check1 -match "FOUND")
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
    $results["company_row_exists"] = $false
} finally {
    Pop-Location
}

Write-Step "filing_row_exists"
Push-Location apps/api
try {
    $script2 = "from gct.database import SessionLocal`nfrom gct.models import Filing, Company`nfrom sqlalchemy import select`nwith SessionLocal() as s:`n    company = s.execute(select(Company).where(Company.ticker == 'AAPL')).scalar_one_or_none()`n    if not company:`n        print('NO_COMPANY')`n    else:`n        filing = s.execute(select(Filing).where(Filing.company_id == company.id)).scalar_one_or_none()`n        print('FOUND' if filing else 'MISSING')"
    $check2 = python -c $script2
    Write-Host "  $check2"
    $results["filing_row_exists"] = ($check2 -match "FOUND")
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
    $results["filing_row_exists"] = $false
} finally {
    Pop-Location
}

Write-Step "auditor_report_exists"
Push-Location apps/api
try {
    $script3 = "from gct.database import SessionLocal`nfrom gct.models import AuditorReport, Filing, Company`nfrom sqlalchemy import select`nwith SessionLocal() as s:`n    company = s.execute(select(Company).where(Company.ticker == 'AAPL')).scalar_one_or_none()`n    if not company:`n        print('NO_COMPANY')`n    else:`n        filing = s.execute(select(Filing).where(Filing.company_id == company.id)).scalar_one_or_none()`n        if not filing:`n            print('NO_FILING')`n        else:`n            report = s.execute(select(AuditorReport).where(AuditorReport.filing_id == filing.id)).scalar_one_or_none()`n            if report and report.report_text and len(report.report_text) > 100:`n                print('FOUND')`n            else:`n                print('MISSING_OR_EMPTY')"
    $check3 = python -c $script3
    Write-Host "  $check3"
    $results["auditor_report_exists"] = ($check3 -match "FOUND")
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
    $results["auditor_report_exists"] = $false
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "============================================"
Write-Host "  INGESTION VERIFICATION REPORT"
Write-Host "============================================"

$passed = 0
$failed = 0
foreach ($key in $results.Keys) {
    Write-Result -Name $key -Passed $results[$key]
    if ($results[$key]) { $passed++ } else { $failed++ }
}

Write-Host "--------------------------------------------"
Write-Host "  PASSED: $passed   FAILED: $failed"
Write-Host "============================================"

if ($failed -eq 0) {
    exit 0
} else {
    exit 1
}
