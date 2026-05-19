#!/usr/bin/env bash
# verify_frontend.sh — Verify the frontend compiles, tests pass, and builds correctly.

set -euo pipefail

PASS=0
FAIL=0

step()  { echo -e "\n==> $1"; }
pass()  { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail()  { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }

# ── 1. Check .env.local ───────────────────────────────────────────────────────
step "Checking apps/web/.env.local"
if [ -f apps/web/.env.local ]; then
    if grep -q "NEXT_PUBLIC_API_BASE_URL" apps/web/.env.local; then
        pass ".env.local exists and contains NEXT_PUBLIC_API_BASE_URL"
    else
        fail ".env.local exists but NEXT_PUBLIC_API_BASE_URL is missing"
    fi
else
    fail ".env.local not found"
fi

# ── 2. Type-check ─────────────────────────────────────────────────────────────
step "Running type-check (tsc --noEmit)"
if (cd apps/web && npm run type-check); then
    pass "TypeScript type-check passed"
else
    fail "TypeScript type-check failed"
fi

# ── 3. Lint ───────────────────────────────────────────────────────────────────
step "Running ESLint"
if (cd apps/web && npm run lint); then
    pass "ESLint passed"
else
    fail "ESLint failed"
fi

# ── 4. Tests ──────────────────────────────────────────────────────────────────
step "Running frontend tests (vitest)"
if (cd apps/web && npm test); then
    pass "Frontend tests passed"
else
    fail "Frontend tests failed"
fi

# ── 5. Build ──────────────────────────────────────────────────────────────────
step "Building Next.js app"
if (cd apps/web && npm run build); then
    pass "Next.js build succeeded"
else
    fail "Next.js build failed"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  FRONTEND VERIFICATION SUMMARY"
echo "========================================"
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "One or more checks failed. See output above."
    exit 1
else
    echo ""
    echo "All checks passed."
    exit 0
fi
