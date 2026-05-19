from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticker: str
    cik: str
    name: str
    sector: str | None
    industry: str | None
    created_at: datetime
    updated_at: datetime


class FilingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    form_type: str
    accession_number: str
    filing_date: date
    period_of_report: date | None
    filing_url: str
    raw_text_path: str | None
    processed_at: datetime | None
    created_at: datetime


class AuditorReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filing_id: uuid.UUID
    audit_firm: str | None
    report_text: str
    extraction_method: str
    extracted_at: datetime


class GoingConcernFlagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filing_id: uuid.UUID
    company_id: uuid.UUID
    severity: str
    flag_type: str
    quoted_language: str
    char_offset_start: int
    char_offset_end: int
    classification_confidence: Decimal
    classifier_version: str
    detected_at: datetime
    created_at: datetime
    notes: str | None


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    confirmed: bool
    created_at: datetime
    unsubscribed_at: datetime | None


class EvalCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filing_accession: str
    expected_has_going_concern: bool
    expected_severity: str | None
    expected_flag_type: str | None
    notes: str | None
    created_at: datetime
