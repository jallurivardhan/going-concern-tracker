from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gct.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable so companies ingested by CIK (with no active ticker) can be stored.
    # PostgreSQL allows multiple NULLs in a unique column — only non-null values
    # are checked for uniqueness.
    ticker: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    cik: Mapped[str] = mapped_column(
        String(10), unique=True, index=True, nullable=False, comment="10-digit zero-padded SEC CIK"
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False, comment="Raw SEC EDGAR legal name — preserved for audit traceability")
    # User-facing display name. NULL means fall back to a humanised version of name.
    display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(256), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    filings: Mapped[list[Filing]] = relationship("Filing", back_populates="company")
    going_concern_flags: Mapped[list[GoingConcernFlag]] = relationship(
        "GoingConcernFlag", back_populates="company"
    )


class Filing(Base):
    __tablename__ = "filings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), index=True, nullable=False
    )
    form_type: Mapped[str] = mapped_column(
        String(20), index=True, nullable=False, comment="e.g. 10-K, 10-Q, 8-K"
    )
    accession_number: Mapped[str] = mapped_column(
        String(25), unique=True, index=True, nullable=False, comment="SEC accession number"
    )
    filing_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    period_of_report: Mapped[date | None] = mapped_column(Date, nullable=True)
    filing_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text_path: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Path or object-storage key to stored full text"
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    company: Mapped[Company] = relationship("Company", back_populates="filings")
    auditor_report: Mapped[AuditorReport | None] = relationship(
        "AuditorReport", back_populates="filing", uselist=False
    )
    going_concern_flags: Mapped[list[GoingConcernFlag]] = relationship(
        "GoingConcernFlag", back_populates="filing"
    )

    __table_args__ = (Index("ix_filings_company_filing_date", "company_id", "filing_date"),)


class AuditorReport(Base):
    __tablename__ = "auditor_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("filings.id"),
        unique=True,
        nullable=False,
        comment="One auditor report per filing",
    )
    audit_firm: Mapped[str | None] = mapped_column(String(256), nullable=True)
    report_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Extracted auditor report section"
    )
    extraction_method: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="e.g. html_section_xpath, fuzzy_match"
    )
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    filing: Mapped[Filing] = relationship("Filing", back_populates="auditor_report")


class GoingConcernFlag(Base):
    __tablename__ = "going_concern_flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filings.id"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), index=True, nullable=False
    )
    # "critical" | "elevated" | "watch"
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    # "new" | "continuing" | "resolved"
    flag_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quoted_language: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Exact paragraph cited from the auditor report"
    )
    char_offset_start: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Byte offset within auditor report text"
    )
    char_offset_end: Mapped[int] = mapped_column(Integer, nullable=False)
    # Use Numeric — never Float — for any financial/confidence value
    classification_confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, comment="e.g. 0.987"
    )
    classifier_version: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="e.g. v1.0-claude-sonnet-4"
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    filing: Mapped[Filing] = relationship("Filing", back_populates="going_concern_flags")
    company: Mapped[Company] = relationship("Company", back_populates="going_concern_flags")

    __table_args__ = (
        Index("ix_gcf_detected_at", "detected_at"),
        Index("ix_gcf_severity_detected_at", "severity", "detected_at"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmation_token: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    unsubscribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PipelineRun(Base):
    """Records metadata about each pipeline execution for observability."""

    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "running" | "success" | "partial_success" | "failure"
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    filings_checked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filings_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filings_classified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flags_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_estimate: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0"), nullable=False
    )
    errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # "scheduled" | "manual"
    trigger: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)

    __table_args__ = (Index("ix_pipeline_runs_started_at", "started_at"),)


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filing_accession: Mapped[str] = mapped_column(
        String(25), index=True, nullable=False
    )
    expected_has_going_concern: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    expected_flag_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
