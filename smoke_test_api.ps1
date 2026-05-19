$BASE_URL = 'http://localhost:8000'
$passes = @()
$fails = @()

function Pass([string]$msg) { $script:passes += $msg; Write-Host "  [PASS] $msg" -ForegroundColor Green }
function Fail([string]$msg) { $script:fails += $msg; Write-Host "  [FAIL] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "=== API SMOKE TEST ===" -ForegroundColor Cyan

# 1. Health
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/health" -UseBasicParsing
    if ($r.StatusCode -eq 200) { Pass "/api/health 200" } else { Fail "/api/health got $($r.StatusCode)" }
} catch { Fail "/api/health threw: $_" }

# 2. Docs
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/docs" -UseBasicParsing
    if ($r.StatusCode -eq 200) { Pass "/api/docs 200" } else { Fail "/api/docs got $($r.StatusCode)" }
} catch { Fail "/api/docs threw: $_" }

# 3. Stats — 2 critical flags
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/stats" -UseBasicParsing
    $d = $r.Content | ConvertFrom-Json
    if ($d.total_flags_active -ge 2) {
        Pass "/api/stats total_flags_active=$($d.total_flags_active)"
    } else {
        Fail "/api/stats total_flags_active=$($d.total_flags_active) expected >= 2"
    }
    if ($d.flag_breakdown.critical -ge 2) {
        Pass "/api/stats flag_breakdown.critical=$($d.flag_breakdown.critical)"
    } else {
        Fail "/api/stats critical=$($d.flag_breakdown.critical) expected >= 2"
    }
    if ($d.total_companies_tracked -ge 8) {
        Pass "/api/stats total_companies=$($d.total_companies_tracked)"
    } else {
        Fail "/api/stats total_companies=$($d.total_companies_tracked) expected >= 8"
    }
} catch { Fail "/api/stats threw: $_" }

# 4. Flags default returns >= 2
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/flags" -UseBasicParsing
    $d = $r.Content | ConvertFrom-Json
    $cnt = $d.items.Count
    if ($cnt -ge 2) {
        Pass "/api/flags default returns $cnt items"
    } else {
        Fail "/api/flags default returned $cnt items (expected >= 2)"
    }
    # Verify citation chain
    foreach ($item in $d.items) {
        if (-not $item.quoted_language) { Fail "Flag $($item.id) missing quoted_language" }
        if (-not $item.filing) { Fail "Flag $($item.id) missing filing" }
        if (-not $item.char_offset_start -and $item.char_offset_start -ne 0) { Fail "Flag $($item.id) missing char_offset_start" }
    }
    if ($cnt -ge 2) { Pass "/api/flags items have citation chain (quoted_language, filing, offsets)" }
} catch { Fail "/api/flags threw: $_" }

# 5. Companies >= 8
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/companies" -UseBasicParsing
    $d = $r.Content | ConvertFrom-Json
    if ($d.items.Count -ge 8) {
        Pass "/api/companies returns $($d.items.Count) companies"
    } else {
        Fail "/api/companies returned $($d.items.Count) (expected >= 8)"
    }
} catch { Fail "/api/companies threw: $_" }

# 6. Company detail
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/companies/0001008654" -UseBasicParsing
    $d = $r.Content | ConvertFrom-Json
    if ($r.StatusCode -eq 200 -and $d.cik -eq "0001008654") {
        Pass "/api/companies/0001008654 returns Tupperware"
    } else {
        Fail "/api/companies/0001008654 unexpected: $($r.Content.Substring(0,100))"
    }
} catch { Fail "/api/companies/0001008654 threw: $_" }

# 7. Search
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/search?q=tupp" -UseBasicParsing
    $d = $r.Content | ConvertFrom-Json
    $match = $d.results | Where-Object { $_.name -like "*Tupperware*" }
    if ($match) {
        Pass "/api/search?q=tupp finds Tupperware"
    } else {
        Fail "/api/search?q=tupp no Tupperware match"
    }
} catch { Fail "/api/search threw: $_" }

# 8. Subscriptions POST
try {
    $email = "smoketest_$(Get-Random)@example.com"
    $body = "{`"email`":`"$email`"}"
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/subscriptions" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
    $d = $r.Content | ConvertFrom-Json
    if ($d.ok -and $d.subscription_id) {
        Pass "/api/subscriptions POST ok=true sub_id=$($d.subscription_id)"
    } else {
        Fail "/api/subscriptions POST unexpected response"
    }
} catch { Fail "/api/subscriptions POST threw: $_" }

# 9. Methodology
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/methodology" -UseBasicParsing
    $d = $r.Content | ConvertFrom-Json
    if ($r.StatusCode -eq 200 -and $d.methodology_version) {
        Pass "/api/methodology returns methodology_version=$($d.methodology_version)"
    } else {
        Fail "/api/methodology missing data"
    }
} catch { Fail "/api/methodology threw: $_" }

Write-Host ""
Write-Host "=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "Passed: $($passes.Count)" -ForegroundColor Green
if ($fails.Count -gt 0) {
    Write-Host "Failed: $($fails.Count)" -ForegroundColor Red
    Write-Host "=== RESULT: FAIL ===" -ForegroundColor Red
    exit 1
} else {
    Write-Host "=== RESULT: PASS ===" -ForegroundColor Green
    Write-Host "OpenAPI docs: $BASE_URL/api/docs" -ForegroundColor Cyan
    exit 0
}
