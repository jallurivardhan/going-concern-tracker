"""Shared fixtures and helpers for API route tests.

All tests mock the database session using dependency_overrides — no live DB.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from gct.database import get_db
from gct.main import app
from gct.models import AuditorReport, Company, Filing, GoingConcernFlag, Subscription

client = TestClient(app)


# ── Factory helpers ───────────────────────────────────────────────────────────


def make_company(
    cik: str = "0001008654",
    ticker: str | None = "TUP",
    name: str = "Tupperware Brands Corp",
) -> MagicMock:
    c = MagicMock(spec=Company)
    c.id = uuid.uuid4()
    c.cik = cik
    c.ticker = ticker
    c.name = name
    c.sector = None
    c.industry = None
    c.created_at = datetime(2026, 1, 1)
    c.updated_at = datetime(2026, 1, 1)
    c.filings = []
    c.going_concern_flags = []
    return c


def make_filing(
    company: MagicMock,
    accession: str = "0001008654-23-000079",
    filing_date: date = date(2023, 10, 13),
) -> MagicMock:
    f = MagicMock(spec=Filing)
    f.id = uuid.uuid4()
    f.company_id = company.id
    f.form_type = "10-K"
    f.accession_number = accession
    f.filing_date = filing_date
    f.period_of_report = None
    f.filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={company.cik}&type=10-K"
    f.raw_text_path = None
    f.processed_at = None
    f.created_at = datetime(2026, 1, 1)
    return f


def make_flag(
    filing: MagicMock,
    company: MagicMock,
    severity: str = "critical",
    confidence: str = "0.990",
) -> MagicMock:
    g = MagicMock(spec=GoingConcernFlag)
    g.id = uuid.uuid4()
    g.filing_id = filing.id
    g.company_id = company.id
    g.severity = severity
    g.flag_type = "new"
    g.quoted_language = "There is substantial doubt about its ability to continue as a going concern."
    g.char_offset_start = 100
    g.char_offset_end = 200
    g.classification_confidence = Decimal(confidence)
    g.classifier_version = "v1.0-claude"
    g.detected_at = datetime(2026, 5, 17, 19, 42, 0)
    g.created_at = datetime(2026, 5, 17, 19, 42, 0)
    g.notes = None
    return g


def make_auditor_report(filing: MagicMock, text: str = "A" * 3000) -> MagicMock:
    ar = MagicMock(spec=AuditorReport)
    ar.id = uuid.uuid4()
    ar.filing_id = filing.id
    ar.audit_firm = "PricewaterhouseCoopers LLP"
    ar.report_text = text
    ar.extraction_method = "html_section"
    ar.extracted_at = datetime(2026, 1, 1)
    return ar


# ── DB mock helpers ────────────────────────────────────────────────────────────


def make_db_override(mock_session: MagicMock) -> Generator[MagicMock, None, None]:
    def override() -> Generator[MagicMock, None, None]:
        yield mock_session
    return override


def patch_db(mock_session: MagicMock) -> None:
    app.dependency_overrides[get_db] = make_db_override(mock_session)


def clear_db() -> None:
    app.dependency_overrides.clear()
