"""Aggregate stats and methodology data for the API.

stats_service: System-wide aggregate counts for the landing page hero section.
              Reads from the database only.

methodology:  Reads the latest benchmark report from the eval/reports/ directory.
              No database access.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gct.models import AuditorReport, Company, Filing, GoingConcernFlag
from gct.schemas.api import (
    EvalMetrics,
    FlagSummary,
    MethodologyResponse,
    RecentFlagBrief,
    StatsResponse,
)

_POSITIVE = ("critical", "elevated", "watch")
_CLASSIFIER_VERSION = "v1.0-claude-haiku-4-5"  # reflects current primary model
_METHODOLOGY_VERSION = "v1.0"
_EVAL_SET_VERSION = "v1.0"

_REPORTS_DIR = Path(__file__).parents[3] / "eval" / "reports"

# Backfilled filings are ingested months/years after filing date; their
# "minutes_to_detect" isn't meaningful.  Suppress it when > 7 days.
_MEANINGFUL_DETECTION_WINDOW = timedelta(days=7)


def get_stats(db: Session) -> StatsResponse:
    """Aggregate system stats — one query per metric group."""
    total_companies = db.execute(select(func.count()).select_from(Company)).scalar() or 0
    total_filings = db.execute(select(func.count()).select_from(Filing)).scalar() or 0
    total_reports = db.execute(select(func.count()).select_from(AuditorReport)).scalar() or 0

    # Flag breakdown
    sev_counts = db.execute(
        select(GoingConcernFlag.severity, func.count().label("cnt"))
        .group_by(GoingConcernFlag.severity)
    ).all()
    breakdown: dict[str, int] = {row[0]: row[1] for row in sev_counts}
    flag_summary = FlagSummary(
        critical=breakdown.get("critical", 0),
        elevated=breakdown.get("elevated", 0),
        watch=breakdown.get("watch", 0),
        none=breakdown.get("none", 0),
    )
    total_active = (
        flag_summary.critical + flag_summary.elevated + flag_summary.watch
    )

    # Most recent critical/elevated/watch flag
    recent_row = db.execute(
        select(GoingConcernFlag, Filing, Company)
        .join(Filing, GoingConcernFlag.filing_id == Filing.id)
        .join(Company, GoingConcernFlag.company_id == Company.id)
        .where(GoingConcernFlag.severity.in_(_POSITIVE))
        .order_by(GoingConcernFlag.detected_at.desc())
        .limit(1)
    ).first()

    most_recent_flag: RecentFlagBrief | None = None
    last_pipeline_run: datetime | None = None

    if recent_row:
        flag, filing, company = recent_row
        last_pipeline_run = flag.detected_at
        # Compare as naive UTC by stripping timezone info from detected_at
        detected_naive = flag.detected_at.replace(tzinfo=None)
        filing_dt = datetime.combine(filing.filing_date, datetime.min.time())
        delta = detected_naive - filing_dt
        minutes = int(delta.total_seconds() / 60)
        most_recent_flag = RecentFlagBrief(
            id=flag.id,
            company_name=company.name,
            company_display_name=company.display_name,
            company_ticker=company.ticker,
            severity=flag.severity,
            filing_date=filing.filing_date,
            detected_at=flag.detected_at,
            minutes_to_detect=minutes if abs(delta) <= _MEANINGFUL_DETECTION_WINDOW else None,
        )

    return StatsResponse(
        total_companies_tracked=total_companies,
        total_filings_analyzed=total_filings,
        total_auditor_reports_extracted=total_reports,
        total_flags_active=total_active,
        flag_breakdown=flag_summary,
        most_recent_critical_flag=most_recent_flag,
        last_pipeline_run=last_pipeline_run,
    )


def get_methodology() -> MethodologyResponse:
    """Build the methodology response, reading the latest eval report if available."""
    current_metrics: EvalMetrics | None = None

    if _REPORTS_DIR.is_dir():
        report_files = sorted(_REPORTS_DIR.glob("*.json"), reverse=True)
        # Skip .gitkeep and read the newest real JSON report
        report_files = [f for f in report_files if f.stat().st_size > 10]
        if report_files:
            latest = report_files[0]
            try:
                data = json.loads(latest.read_text(encoding="utf-8"))
                current_metrics = EvalMetrics(
                    total_cases=data["total_cases"],
                    precision=Decimal(data["precision"]),
                    recall=Decimal(data["recall"]),
                    f1=Decimal(data["f1"]),
                    accuracy=Decimal(data["accuracy"]),
                    last_run=datetime.fromisoformat(data["timestamp"]),
                )
            except (KeyError, ValueError, json.JSONDecodeError):
                current_metrics = None

    return MethodologyResponse(
        methodology_version=_METHODOLOGY_VERSION,
        classifier_version=_CLASSIFIER_VERSION,
        eval_set_version=_EVAL_SET_VERSION,
        current_metrics=current_metrics,
        in_scope=[
            "10-K annual filings",
            "Auditor's report section only",
            "PCAOB AS 2415 going-concern language",
            "US public companies registered with SEC",
        ],
        out_of_scope=[
            "10-Q quarterly filings",
            "Management MD&A disclosures",
            "Note-level going-concern disclosures (e.g., Note 1, Note 19)",
            "Foreign private issuer filings (20-F, 40-F)",
            "8-K material event filings",
            "Mid-year going-concern events",
        ],
    )
