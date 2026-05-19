#!/usr/bin/env bash
# verify_api.sh — Smoke test for the Going Concern Tracker REST API (Linux/macOS)
#
# Usage (from repo root):
#   cd apps/api
#   bash ../../verify_api.sh
#
# Prerequisites: DATABASE_URL set in .env or environment.

set -euo pipefail

API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/apps/api" && pwd)"
BASE_URL="http://localhost:8000"
PASSES=0
FAILS=0

pass() { PASSES=$((PASSES + 1)); echo "  [PASS] $1"; }
fail() { FAILS=$((FAILS + 1)); echo "  [FAIL] $1" >&2; }

status_code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
json_body()   { curl -s "$@"; }

echo ""
echo "=== GOING CONCERN TRACKER — API SMOKE TEST ==="
echo "Working directory: $API_DIR"
echo ""

# ── Start server ──────────────────────────────────────────────────────────────
echo "Starting FastAPI server..."
cd "$API_DIR"
python -m uvicorn gct.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
sleep 4

cleanup() {
    echo ""
    echo "Stopping server (PID $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── Tests ─────────────────────────────────────────────────────────────────────

# 1. Health
CODE=$(status_code "$BASE_URL/api/health")
[ "$CODE" -eq 200 ] && pass "/api/health returns 200" || fail "/api/health got $CODE"

# 2. OpenAPI docs
CODE=$(status_code "$BASE_URL/api/docs")
[ "$CODE" -eq 200 ] && pass "/api/docs renders (200)" || fail "/api/docs got $CODE"

# 3. Stats
BODY=$(json_body "$BASE_URL/api/stats")
ACTIVE=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['total_flags_active'])")
[ "$ACTIVE" -ge 2 ] && pass "/api/stats total_flags_active=$ACTIVE >= 2" || fail "/api/stats total_flags_active=$ACTIVE < 2"
COMPANIES=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['total_companies_tracked'])")
[ "$COMPANIES" -ge 8 ] && pass "/api/stats total_companies_tracked=$COMPANIES >= 8" || fail "/api/stats total_companies_tracked=$COMPANIES < 8"

# 4. Flags
BODY=$(json_body "$BASE_URL/api/flags")
COUNT=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['total_returned'])")
[ "$COUNT" -ge 2 ] && pass "/api/flags default returns $COUNT items >= 2" || fail "/api/flags returned $COUNT < 2"

# 5. Flag 404
CODE=$(status_code "$BASE_URL/api/flags/00000000-0000-0000-0000-000000000000")
[ "$CODE" -eq 404 ] && pass "/api/flags/{unknown_id} returns 404" || fail "/api/flags/{unknown_id} got $CODE"

# 6. Companies
BODY=$(json_body "$BASE_URL/api/companies")
COUNT=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['items']))")
[ "$COUNT" -ge 8 ] && pass "/api/companies returns $COUNT items >= 8" || fail "/api/companies returned $COUNT < 8"

# 7. Company detail
CODE=$(status_code "$BASE_URL/api/companies/0001008654")
[ "$CODE" -eq 200 ] && pass "/api/companies/0001008654 returns 200" || fail "/api/companies/0001008654 got $CODE"

# 8. Company 404
CODE=$(status_code "$BASE_URL/api/companies/0000000000")
[ "$CODE" -eq 404 ] && pass "/api/companies/{unknown} returns 404" || fail "/api/companies/{unknown} got $CODE"

# 9. Search
BODY=$(json_body "$BASE_URL/api/search?q=tupp")
HAS_TUPP=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(any('Tupperware' in r['name'] for r in d['results']))")
[ "$HAS_TUPP" = "True" ] && pass "/api/search?q=tupp finds Tupperware" || fail "/api/search?q=tupp no match"

# 10. Search short query → 422
CODE=$(status_code "$BASE_URL/api/search?q=a")
[ "$CODE" -eq 422 ] && pass "/api/search?q=a returns 422" || fail "/api/search?q=a got $CODE"

# 11. Methodology
CODE=$(status_code "$BASE_URL/api/methodology")
[ "$CODE" -eq 200 ] && pass "/api/methodology returns 200" || fail "/api/methodology got $CODE"

# 12. Subscriptions POST
EMAIL="verify_api_$(date +%s)@example.com"
BODY=$(curl -s -X POST "$BASE_URL/api/subscriptions" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\"}")
OK=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ok',''))")
SUB_ID=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('subscription_id',''))")
[ "$OK" = "True" ] && [ -n "$SUB_ID" ] && pass "/api/subscriptions POST ok=true sub_id=$SUB_ID" || fail "/api/subscriptions POST: $BODY"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== SUMMARY ==="
echo "Passed: $PASSES"
echo "Failed: $FAILS"
echo ""
if [ "$FAILS" -gt 0 ]; then
    echo "=== RESULT: FAIL ==="
    exit 1
else
    echo "=== RESULT: PASS ==="
    echo "OpenAPI docs: $BASE_URL/api/docs"
    exit 0
fi
