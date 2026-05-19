#!/usr/bin/env bash
# Smoke-test for the Tier-2 classification layer (bash equivalent of verify_classifier.ps1).
# Primary verification script is verify_classifier.ps1 (PowerShell).
#
# Usage: ./verify_classifier.sh

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0
FAIL=0

pass() { echo "  [PASS] $1"; ((PASS++)); }
fail() { echo "  [FAIL] $1"; ((FAIL++)); }

echo ""
echo "=== Going Concern Tracker — Classifier Smoke Test ==="
echo ""

# ── Step 1: Env vars ──────────────────────────────────────────────────────────
echo "[ 1/4 ] Checking environment variables..."

# Source .env if not already set
if [ -f "$REPO_ROOT/.env" ]; then
    set -a; source "$REPO_ROOT/.env"; set +a
fi

for var in ANTHROPIC_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
    if [ -n "${!var:-}" ]; then
        pass "$var is set"
    else
        fail "$var is NOT set"
    fi
done

if [ "$FAIL" -gt 0 ]; then
    echo "Environment checks failed. Fix before continuing."
    exit 1
fi

# ── Step 2: Smoke-test classification ────────────────────────────────────────
echo ""
echo "[ 2/4 ] Running smoke-test classification (AAPL, --limit 1)..."

cd "$REPO_ROOT/apps/api"
output=$(python -m gct.cli.classify --tickers AAPL --limit 1 --force 2>&1) && exit_code=0 || exit_code=$?
echo "$output"

if [ "$exit_code" -eq 0 ]; then
    pass "classify command exited successfully"
else
    fail "classify command exited with code $exit_code"
fi

# ── Step 3: DB check ──────────────────────────────────────────────────────────
echo ""
echo "[ 3/4 ] Querying database for AAPL GoingConcernFlag rows..."

db_result=$(python -c "
from sqlalchemy import text
from gct.database import SessionLocal

db = SessionLocal()
try:
    rows = db.execute(text('''
        SELECT f.filing_date, gcf.severity, gcf.classification_confidence
        FROM going_concern_flags gcf
        JOIN filings f ON f.id = gcf.filing_id
        JOIN companies c ON c.id = gcf.company_id
        WHERE c.ticker = 'AAPL'
        ORDER BY f.filing_date DESC LIMIT 3
    ''')).fetchall()
    if rows:
        for r in rows:
            print(f'  {r.filing_date}  severity={r.severity}  conf={r.classification_confidence}')
        print('OK')
    else:
        print('NO_ROWS')
finally:
    db.close()
" 2>&1)

echo "$db_result"

if echo "$db_result" | grep -q "OK"; then
    pass "GoingConcernFlag row(s) found in database"
elif echo "$db_result" | grep -q "NO_ROWS"; then
    fail "No GoingConcernFlag rows found for AAPL"
else
    fail "Unexpected database result"
fi

# ── Step 4: Cost check ────────────────────────────────────────────────────────
echo ""
echo "[ 4/4 ] Checking cost estimate..."

if echo "$output" | grep -oP '\$\K[0-9]+\.[0-9]+' | awk '{if ($1 < 0.01) exit 0; else exit 1}' 2>/dev/null; then
    pass "Cost is under \$0.01 (expected for one AAPL report)"
else
    echo "  [WARN] Could not confirm cost < \$0.01 from output"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  PASS: $PASS    FAIL: $FAIL"
if [ "$FAIL" -eq 0 ]; then
    echo "  SMOKE TEST PASSED"
    echo ""
    echo "  Ready for full classification run:"
    echo "      cd apps/api && python -m gct.cli.classify"
    echo "  Then verify in Langfuse dashboard."
else
    echo "  SMOKE TEST FAILED"
    exit 1
fi
echo "========================================"
echo ""
