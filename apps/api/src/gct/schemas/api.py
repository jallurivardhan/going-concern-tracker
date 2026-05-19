"""API response schemas for the Going Concern Tracker REST API.

These are separate from the ORM models in ``gct.models``.  They define the
public API surface — callers should not depend on the ORM column layout.

Decimal serialization:
    All ``Decimal`` fields (confidence, metrics) are serialized as JSON strings
    to avoid floating-point coercion.  For example, ``Decimal("0.990")`` produces
    the JSON value ``"0.990"`` rather than ``0.99``.  Callers that need a float
    for display can cast: ``parseFloat(confidence)``.

    Implementation: we use a module-level ``DecimalStr`` type alias that wraps
    ``Decimal`` with a Pydantic ``PlainSerializer``.  Every model that exposes a
    Decimal field uses this alias.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer, model_validator

# ── Decimal → string serializer ──────────────────────────────────────────────
# Pydantic v2: PlainSerializer overrides the JSON encoder for the annotated type.
DecimalStr = Annotated[Decimal, PlainSerializer(lambda d: str(d), return_type=str)]

_COMMON_CONFIG = ConfigDict(from_attributes=True)


def _humanize_name(legal_name: str) -> str:
    """Return a human-readable version of a SEC legal name.

    If the name is entirely upper-case (e.g. "TUPPERWARE BRANDS CORP") we
    apply title-casing.  Mixed-case names like "Apple Inc." or "WeWork Inc."
    are returned unchanged so we don't mangle intentional capitalisation.
    """
    stripped = legal_name.strip()
    # A name is "all-caps" when every alphabetic character is uppercase.
    if stripped == stripped.upper():
        return stripped.title()
    return stripped


# ── Nested inline models ──────────────────────────────────────────────────────


class CompanyBrief(BaseModel):
    """Compact company reference embedded in flag/filing responses."""
    model_config = _COMMON_CONFIG
    cik: str
    ticker: str | None
    name: str
    display_name: str | None = None

    @model_validator(mode="after")
    def _fill_display_name(self) -> "CompanyBrief":
        if not self.display_name:
            self.display_name = _humanize_name(self.name)
        return self


class FilingBrief(BaseModel):
    """Compact filing reference embedded in flag responses."""
    model_config = _COMMON_CONFIG
    id: uuid.UUID
    accession_number: str
    form_type: str
    filing_date: date
    period_of_report: date | None = None
    filing_url: str


class FlagBrief(BaseModel):
    """Compact flag reference embedded in company/filing responses."""
    model_config = _COMMON_CONFIG
    id: uuid.UUID
    severity: str
    filing_date: date
    detected_at: datetime


# ── Flag responses ────────────────────────────────────────────────────────────


class FlagResponse(BaseModel):
    """Full going-concern flag — used in feed and detail views."""
    model_config = _COMMON_CONFIG

    id: uuid.UUID
    company: CompanyBrief
    filing: FilingBrief
    severity: str
    flag_type: str
    quoted_language: str
    char_offset_start: int
    char_offset_end: int
    classification_confidence: DecimalStr
    classifier_version: str
    detected_at: datetime
    audit_firm: str | None


class FlagDetailResponse(FlagResponse):
    """Extended flag — detail view adds the auditor report excerpt."""
    report_excerpt: str | None
    report_total_length: int | None


class FlagListResponse(BaseModel):
    """Paginated list of flags."""
    items: list[FlagResponse]
    next_cursor: str | None
    has_more: bool
    total_returned: int


# ── Company responses ─────────────────────────────────────────────────────────


class FlagSummary(BaseModel):
    critical: int = 0
    elevated: int = 0
    watch: int = 0
    none: int = 0


class CompanyResponse(BaseModel):
    """Company list item — includes aggregated flag counts."""
    model_config = _COMMON_CONFIG

    cik: str
    ticker: str | None
    name: str
    display_name: str | None = None
    sector: str | None
    industry: str | None
    total_filings: int
    total_10ks: int
    flag_summary: FlagSummary
    most_recent_flag: FlagBrief | None

    @model_validator(mode="after")
    def _fill_display_name(self) -> "CompanyResponse":
        if not self.display_name:
            self.display_name = _humanize_name(self.name)
        return self


class CompanyDetailResponse(CompanyResponse):
    """Company detail — adds flag history and most recent filing date."""
    most_recent_filing_date: date | None
    flag_history: list[FlagResponse]
    filings: list[FilingResponse]


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    next_cursor: str | None
    has_more: bool


# ── Filing responses ──────────────────────────────────────────────────────────


class FilingResponse(BaseModel):
    """Filing detail — includes company, auditor excerpt, and linked flag."""
    model_config = _COMMON_CONFIG

    id: uuid.UUID
    accession_number: str
    form_type: str
    filing_date: date
    period_of_report: date | None
    filing_url: str
    company: CompanyBrief
    auditor_report_excerpt: str | None  # first 2000 chars of auditor report
    audit_firm: str | None
    going_concern_flag: FlagResponse | None


class FilingListResponse(BaseModel):
    items: list[FilingResponse]
    next_cursor: str | None
    has_more: bool


# ── Search responses ──────────────────────────────────────────────────────────


class SearchResult(BaseModel):
    cik: str
    ticker: str | None
    name: str
    display_name: str | None = None
    match_type: str  # "ticker_exact" | "ticker_prefix" | "name_substring"
    has_critical_flag: bool


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    total_returned: int


# ── Stats response ────────────────────────────────────────────────────────────


class RecentFlagBrief(BaseModel):
    id: uuid.UUID
    company_name: str
    company_display_name: str | None = None
    company_ticker: str | None
    severity: str
    filing_date: date
    detected_at: datetime
    minutes_to_detect: int | None


class StatsResponse(BaseModel):
    total_companies_tracked: int
    total_filings_analyzed: int
    total_auditor_reports_extracted: int
    total_flags_active: int
    flag_breakdown: FlagSummary
    most_recent_critical_flag: RecentFlagBrief | None
    last_pipeline_run: datetime | None


# ── Methodology response ──────────────────────────────────────────────────────


class EvalMetrics(BaseModel):
    total_cases: int
    precision: DecimalStr
    recall: DecimalStr
    f1: DecimalStr
    accuracy: DecimalStr
    last_run: datetime


class MethodologyResponse(BaseModel):
    methodology_version: str
    classifier_version: str
    eval_set_version: str
    current_metrics: EvalMetrics | None
    in_scope: list[str]
    out_of_scope: list[str]


# ── Pipeline responses ────────────────────────────────────────────────────────


class PipelineRunBrief(BaseModel):
    model_config = _COMMON_CONFIG
    id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None
    status: str
    filings_checked: int
    filings_new: int
    filings_classified: int
    flags_created: int
    total_cost_estimate: DecimalStr
    trigger: str


class PipelineStatusResponse(BaseModel):
    last_successful_run: PipelineRunBrief | None
    last_run: PipelineRunBrief | None
    watchlist_size: int
    schedule: str = "daily 6am UTC"


# ── Subscription responses ────────────────────────────────────────────────────


class SubscriptionRequest(BaseModel):
    email: str  # validated by the route using EmailStr


class SubscriptionResponse(BaseModel):
    ok: bool
    message: str
    subscription_id: uuid.UUID | None = None
    already_subscribed: bool = False


class UnsubscribeResponse(BaseModel):
    ok: bool
    message: str
