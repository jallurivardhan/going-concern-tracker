#!/usr/bin/env bash
# verify.sh — End-of-prompt verification script for Going Concern Tracker bootstrap.
# Safe to re-run. Exits 0 if all checks pass, 1 if any fail.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"

PASS=0
FAIL=0

declare -A RESULTS

run_step() {
  local name="$1"
  shift
  echo ""
  echo "▶ $name"
  if "$@"; then
    RESULTS["$name"]="PASS"
    ((PASS++)) || true
  else
    RESULTS["$name"]="FAIL"
    ((FAIL++)) || true
  fi
}

# ── 1. Node version ≥ 20 ────────────────────────────────────────────────────
check_node() {
  local version
  version=$(node --version 2>/dev/null | sed 's/v//')
  local major="${version%%.*}"
  echo "  node $version"
  [[ "$major" -ge 20 ]]
}
run_step "node_version" check_node

# ── 2. Python version ≥ 3.11 ────────────────────────────────────────────────
check_python() {
  local version
  version=$(python3 --version 2>/dev/null | awk '{print $2}')
  local major minor
  IFS='.' read -r major minor _ <<< "$version"
  echo "  python $version"
  [[ "$major" -eq 3 && "$minor" -ge 11 ]]
}
run_step "python_version" check_python

# ── 3. .env exists with DATABASE_URL ────────────────────────────────────────
check_env() {
  if [[ ! -f "$ROOT/.env" ]]; then
    echo "  .env file not found. Copy .env.example to .env and fill in values."
    return 1
  fi
  if grep -q "^DATABASE_URL=" "$ROOT/.env"; then
    echo "  DATABASE_URL is set ✓"
    return 0
  else
    echo "  DATABASE_URL not found in .env"
    return 1
  fi
}
run_step "env_file" check_env

# ── 4. Install Python dependencies ──────────────────────────────────────────
install_python_deps() {
  cd "$API_DIR"
  pip install -e ".[dev]" --quiet
}
run_step "pip_install" install_python_deps

# ── 5. Generate initial migration ───────────────────────────────────────────
generate_migration() {
  cd "$API_DIR"
  # Only generate if no migration files exist yet
  if ls alembic/versions/*.py 2>/dev/null | grep -v __pycache__ | head -1 | grep -q ".py"; then
    echo "  Migration already exists, skipping generation."
    return 0
  fi
  alembic revision --autogenerate -m "initial schema"
}
run_step "migration_generate" generate_migration

# ── 6. Apply migration ───────────────────────────────────────────────────────
apply_migration() {
  cd "$API_DIR"
  alembic upgrade head
}
run_step "migration_apply" apply_migration

# ── 7. Backend tests ─────────────────────────────────────────────────────────
run_backend_tests() {
  cd "$API_DIR"
  pytest tests/test_health.py tests/test_edgar_client.py tests/test_ticker_lookup.py tests/test_filing_parser.py -v
}
run_step "backend_tests" run_backend_tests

# ── 8. Frontend npm install ──────────────────────────────────────────────────
install_frontend_deps() {
  cd "$WEB_DIR"
  npm install --silent
}
run_step "npm_install" install_frontend_deps

# ── 9. Frontend type-check ───────────────────────────────────────────────────
frontend_typecheck() {
  cd "$WEB_DIR"
  npm run type-check
}
run_step "frontend_typecheck" frontend_typecheck

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  GOING CONCERN TRACKER BOOTSTRAP REPORT"
echo "════════════════════════════════════════════"
for step in node_version python_version env_file pip_install migration_generate migration_apply backend_tests npm_install frontend_typecheck; do
  status="${RESULTS[$step]:-SKIP}"
  printf "  %-30s %s\n" "$step" "$status"
done
echo "────────────────────────────────────────────"
echo "  PASSED: $PASS   FAILED: $FAIL"
echo "════════════════════════════════════════════"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
