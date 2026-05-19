"""One-off data fix: Beyond, Inc. (CIK 0001130713) was wrongly ingested as BBBY.

Background
----------
A ticker-based backfill resolved "BBBY" to CIK 0001130713.  That CIK belongs to
Beyond, Inc. — the post-bankruptcy successor that adopted the BBBY ticker after
the original Bed Bath & Beyond Inc. (CIK 0000886158) went bankrupt in April
2023.  The original company's going-concern filings therefore never made it into
the database.

This script relabels the mislabelled row so the company reflects its true
identity: Beyond, Inc., ticker BYON.

Safety
------
- Idempotent: safe to re-run.  If the row is already labelled correctly the
  script prints a message and exits cleanly without modifying the database.
- Does NOT touch AuditorReport or GoingConcernFlag rows — those were correctly
  classified given the data they were given (Beyond, Inc. is a healthy company).

Usage
-----
    cd apps/api
    python scripts/fix_bbby_mislabel.py
"""

from gct.database import SessionLocal
from gct.models import Company
from sqlalchemy import select

TARGET_CIK = "0001130713"
CORRECT_TICKER = "BYON"
CORRECT_NAME = "Beyond, Inc."


def main() -> None:
    db = SessionLocal()
    try:
        company = db.execute(
            select(Company).where(Company.cik == TARGET_CIK)
        ).scalar_one_or_none()

        if company is None:
            print(f"CIK {TARGET_CIK} not found in database; nothing to do.")
            return

        # Idempotency: already correct?
        if company.ticker == CORRECT_TICKER and company.name == CORRECT_NAME:
            print(
                f"CIK {TARGET_CIK} is already labelled correctly "
                f"(ticker={CORRECT_TICKER!r}, name={CORRECT_NAME!r}); nothing to do."
            )
            return

        old_ticker = company.ticker
        old_name = company.name

        company.ticker = CORRECT_TICKER
        company.name = CORRECT_NAME
        db.commit()

        print(
            f"Updated CIK {TARGET_CIK}:\n"
            f"  ticker: {old_ticker!r} -> {CORRECT_TICKER!r}\n"
            f"  name:   {old_name!r} -> {CORRECT_NAME!r}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
