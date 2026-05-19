"""Tests verifying the SQL CHECK constraints on core tables.

These tests use a live database session to confirm that violating each
constraint raises an IntegrityError.  They are intentionally destructive
(they attempt to insert bad data and roll back), so they must be isolated
from other test data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from gct.database import SessionLocal
from gct.models import Company, Filing, GoingConcernFlag


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def clean_company(db) -> Company:
    """Insert a company for use in constraint tests, rolling back after."""
    c = Company(
        id=uuid.uuid4(),
        cik="9999999999",
        name="Test Constraint Company",
        display_name="Test Co",
    )
    db.add(c)
    db.flush()
    yield c
    db.rollback()


@pytest.fixture()
def clean_filing(db, clean_company) -> Filing:
    f = Filing(
        id=uuid.uuid4(),
        company_id=clean_company.id,
        form_type="10-K",
        accession_number="9999999999-99-999999",
        filing_date=date(2024, 1, 1),
        filing_url="https://example.com/test.htm",
    )
    db.add(f)
    db.flush()
    yield f


class TestConfidenceInRange:
    def test_above_one_rejected(self, db, clean_filing):
        flag = GoingConcernFlag(
            id=uuid.uuid4(),
            filing_id=clean_filing.id,
            company_id=clean_filing.company_id,
            severity="none",
            flag_type="none",
            quoted_language=None,
            char_offset_start=0,
            char_offset_end=0,
            classification_confidence=Decimal("1.5"),  # violates constraint
            classifier_version="v1.0",
            detected_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db.add(flag)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_negative_rejected(self, db, clean_filing):
        flag = GoingConcernFlag(
            id=uuid.uuid4(),
            filing_id=clean_filing.id,
            company_id=clean_filing.company_id,
            severity="none",
            flag_type="none",
            quoted_language=None,
            char_offset_start=0,
            char_offset_end=0,
            classification_confidence=Decimal("-0.1"),  # violates constraint
            classifier_version="v1.0",
            detected_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db.add(flag)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


class TestCikFormat:
    def test_short_cik_rejected(self, db):
        c = Company(
            id=uuid.uuid4(),
            cik="12345",  # only 5 digits — violates constraint
            name="Bad CIK Company",
        )
        db.add(c)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_alpha_cik_rejected(self, db):
        c = Company(
            id=uuid.uuid4(),
            cik="ABC1234567",  # contains letters — violates constraint
            name="Alpha CIK Company",
        )
        db.add(c)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


class TestFilingDateNotFuture:
    def test_future_date_rejected(self, db, clean_company):
        f = Filing(
            id=uuid.uuid4(),
            company_id=clean_company.id,
            form_type="10-K",
            accession_number="9999999999-99-888888",
            filing_date=date(2099, 1, 1),  # future — violates constraint
            filing_url="https://example.com/future.htm",
        )
        db.add(f)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
