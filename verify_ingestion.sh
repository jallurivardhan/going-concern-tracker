#!/usr/bin/env bash
# verify_ingestion.sh — Manual verification gate for the ingestion layer.
#
# REQUIREMENTS:
#   - Internet access (makes real SEC EDGAR HTTP calls)
#   - .env must contain SEC_USER_AGENT_EMAIL set to your real email
#   - .env must contain a valid DATABASE_URL
#
# Run AFTER main verify.sh passes:
#   bash verify_ingestion.sh
#
# This script is intentionally separate from verify.sh because it hits
# the live SEC EDGAR API and a real Postgres database.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT/apps/api"

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

# ── 1. SEC_USER_AGENT_EMAIL is set ──────────────────────────────────────────
check_sec_email() {
  if [[ ! -f "$ROOT/.env" ]]; then
    echo "  .env file not found"
    return 1
  fi
  if grep -q "^SEC_USER_AGENT_EMAIL=\S" "$ROOT/.env"; then
    local email
    email=$(grep "^SEC_USER_AGENT_EMAIL=" "$ROOT/.env" | cut -d= -f2)
    echo "  SEC_USER_AGENT_EMAIL is set ✓"
    return 0
  else
    echo "  SEC_USER_AGENT_EMAIL is missing or empty in .env"
    echo "  Add:  SEC_USER_AGENT_EMAIL=your.email@example.com"
    return 1
  fi
}
run_step "sec_email_configured" check_sec_email

# ── 2. Run small ingestion: AAPL, 1 10-K, no 10-Q ──────────────────────────
run_small_ingestion() {
  cd "$API_DIR"
  echo "  Running: python -m gct.cli.backfill --tickers AAPL --max-10k 1 --max-10q 0"
  python -m gct.cli.backfill --tickers AAPL --max-10k 1 --max-10q 0
}
run_step "small_ingestion" run_small_ingestion

# ── 3. Verify Apple appears in companies table ──────────────────────────────
check_company_row() {
  cd "$API_DIR"
  python - <<'PYEOF'
from gct.database import SessionLocal
from gct.models import Company
from sqlalchemy import select
db = SessionLocal()
try:
    row = db.execute(select(Company).where(Company.ticker == "AAPL")).scalar_one_or_none()
    if row:
        print(f"  Company row: AAPL / CIK {row.cik} / {row.name} ✓")
        exit(0)
    else:
        print("  AAPL not found in companies table")
        exit(1)
finally:
    db.close()
PYEOF
}
run_step "company_row_exists" check_company_row

# ── 4. Verify at least one filing row exists ─────────────────────────────────
check_filing_row() {
  cd "$API_DIR"
  python - <<'PYEOF'
from gct.database import SessionLocal
from gct.models import Company, Filing
from sqlalchemy import select
db = SessionLocal()
try:
    company = db.execute(select(Company).where(Company.ticker == "AAPL")).scalar_one_or_none()
    if not company:
        print("  No AAPL company row — run ingestion first")
        exit(1)
    filings = db.execute(select(Filing).where(Filing.company_id == company.id)).scalars().all()
    if filings:
        print(f"  {len(filings)} filing(s) found for AAPL ✓")
        for f in filings[:3]:
            print(f"    {f.form_type}  {f.filing_date}  {f.accession_number}")
        exit(0)
    else:
        print("  No filing rows found for AAPL")
        exit(1)
finally:
    db.close()
PYEOF
}
run_step "filing_row_exists" check_filing_row

# ── 5. Verify auditor report row exists with non-empty text ─────────────────
check_auditor_report() {
  cd "$API_DIR"
  python - <<'PYEOF'
from gct.database import SessionLocal
from gct.models import AuditorReport, Company, Filing
from sqlalchemy import select
db = SessionLocal()
try:
    company = db.execute(select(Company).where(Company.ticker == "AAPL")).scalar_one_or_none()
    if not company:
        print("  No AAPL company row")
        exit(1)
    filing = db.execute(
        select(Filing)
        .where(Filing.company_id == company.id, Filing.form_type == "10-K")
        .order_by(Filing.filing_date.desc())
    ).scalars().first()
    if not filing:
        print("  No 10-K filing found for AAPL")
        exit(1)
    report = db.execute(
        select(AuditorReport).where(AuditorReport.filing_id == filing.id)
    ).scalar_one_or_none()
    if report and len(report.report_text) > 100:
        print(f"  Auditor report found: firm={report.audit_firm!r} chars={len(report.report_text)} ✓")
        exit(0)
    elif report:
        print(f"  Auditor report exists but text is too short ({len(report.report_text)} chars)")
        exit(1)
    else:
        print("  No auditor report row found for the 10-K filing")
        exit(1)
finally:
    db.close()
PYEOF
}
run_step "auditor_report_exists" check_auditor_report

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  INGESTION VERIFICATION REPORT"
echo "════════════════════════════════════════════"
for step in sec_email_configured small_ingestion company_row_exists filing_row_exists auditor_report_exists; do
  status="${RESULTS[$step]:-SKIP}"
  printf "  %-35s %s\n" "$step" "$status"
done
echo "────────────────────────────────────────────"
echo "  PASSED: $PASS   FAILED: $FAIL"
echo "════════════════════════════════════════════"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
