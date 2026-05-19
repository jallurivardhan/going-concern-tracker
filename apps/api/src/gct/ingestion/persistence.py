"""Idempotent database writes for the ingestion pipeline.

All functions use PostgreSQL's ``INSERT … ON CONFLICT DO UPDATE`` so that
re-running the backfill for the same company/filing is safe — it updates
metadata without creating duplicate rows.

The natural uniqueness keys are:
  - Company:      cik  (SEC Central Index Key — globally unique)
  - Filing:       accession_number  (SEC assigned, globally unique)
  - AuditorReport: filing_id  (one report per filing)

Raw filing HTML is written to the local filesystem under ``INGESTION_DATA_DIR``
before the DB row is created.  This gives us a reproducible source for
re-extraction without another EDGAR HTTP call.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from gct.config import settings
from gct.ingestion.filing_fetcher import FetchedFiling
from gct.ingestion.filing_parser import AuditorReportExtraction
from gct.models import AuditorReport, Company, Filing

logger = logging.getLogger(__name__)


# ── raw HTML storage ────────────────────────────────────────────────────────


def save_raw_html(cik: str, accession_number: str, html: str) -> str:
    """Write raw filing HTML to disk and return the relative path.

    Path format: ``{INGESTION_DATA_DIR}/{cik}/{accession_number}.html``
    The directory is created if it doesn't exist.
    """
    base = Path(settings.ingestion_data_dir)
    company_dir = base / cik
    company_dir.mkdir(parents=True, exist_ok=True)
    filepath = company_dir / f"{accession_number}.html"
    filepath.write_text(html, encoding="utf-8")
    logger.debug("Saved raw HTML → %s", filepath)
    return str(filepath)


# ── upsert helpers ──────────────────────────────────────────────────────────


def upsert_company(
    session: Session,
    ticker: str | None,
    cik: str,
    name: str,
    sector: str | None = None,
    industry: str | None = None,
) -> Company:
    """Insert or update a Company row keyed on ``cik``.

    ``created_at`` is preserved on update (set only on first insert).
    ``updated_at`` is always refreshed.

    Ticker handling on conflict:
      - If the new ticker is non-null it replaces the stored value (e.g. a
        re-label from a bad ingestion).
      - If the new ticker is null (CIK-only ingestion) the existing non-null
        value is preserved via COALESCE so we never wipe a valid ticker.
    """
    from sqlalchemy import func  # local import to keep top-level imports clean

    now = datetime.utcnow()
    ticker_val = ticker.upper() if ticker else None
    insert_stmt = pg_insert(Company).values(
        id=uuid.uuid4(),
        ticker=ticker_val,
        cik=cik,
        name=name,
        sector=sector,
        industry=industry,
        created_at=now,
        updated_at=now,
    )
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["cik"],
        set_={
            # Preserve an existing non-null ticker when the new value is null.
            "ticker": func.coalesce(insert_stmt.excluded.ticker, Company.ticker),
            "name": name,
            "sector": sector,
            "industry": industry,
            "updated_at": now,
        },
    )
    session.execute(stmt)
    return session.execute(
        select(Company).where(Company.cik == cik)
    ).scalar_one()


def upsert_filing(
    session: Session,
    company_id: uuid.UUID,
    fetched: FetchedFiling,
    raw_text_path: str | None = None,
) -> Filing:
    """Insert or update a Filing row keyed on ``accession_number``.

    On conflict (same accession) we update ``raw_text_path`` and
    ``processed_at`` so a re-run reflects the latest on-disk state.
    """
    now = datetime.utcnow()
    stmt = (
        pg_insert(Filing)
        .values(
            id=uuid.uuid4(),
            company_id=company_id,
            form_type=fetched.form_type,
            accession_number=fetched.accession_number,
            filing_date=fetched.filing_date,
            period_of_report=fetched.period_of_report,
            filing_url=fetched.filing_url,
            raw_text_path=raw_text_path,
            processed_at=now,
            created_at=now,
        )
        .on_conflict_do_update(
            index_elements=["accession_number"],
            set_={
                "raw_text_path": raw_text_path,
                "processed_at": now,
            },
        )
    )
    session.execute(stmt)
    return session.execute(
        select(Filing).where(Filing.accession_number == fetched.accession_number)
    ).scalar_one()


def upsert_auditor_report(
    session: Session,
    filing_id: uuid.UUID,
    extraction: AuditorReportExtraction,
) -> AuditorReport:
    """Insert or update the AuditorReport row for a filing.

    There is at most one auditor report per filing; on conflict all fields
    are refreshed so a re-extraction with an improved parser takes effect.
    """
    now = datetime.utcnow()
    stmt = (
        pg_insert(AuditorReport)
        .values(
            id=uuid.uuid4(),
            filing_id=filing_id,
            audit_firm=extraction.audit_firm,
            report_text=extraction.report_text,
            extraction_method=extraction.extraction_method,
            extracted_at=now,
        )
        .on_conflict_do_update(
            index_elements=["filing_id"],
            set_={
                "audit_firm": extraction.audit_firm,
                "report_text": extraction.report_text,
                "extraction_method": extraction.extraction_method,
                "extracted_at": now,
            },
        )
    )
    session.execute(stmt)
    return session.execute(
        select(AuditorReport).where(AuditorReport.filing_id == filing_id)
    ).scalar_one()
