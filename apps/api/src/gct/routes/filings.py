"""GET /api/filings/{filing_id}."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from gct.database import get_db
from gct.models import AuditorReport, Company, Filing, GoingConcernFlag
from gct.schemas.api import CompanyBrief, FilingResponse
from gct.services.flag_service import _to_flag_response

router = APIRouter(prefix="/filings", tags=["filings"])


@router.get(
    "/{filing_id}",
    response_model=FilingResponse,
    summary="Single filing with auditor report excerpt and linked flag",
)
def get_filing(
    filing_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FilingResponse:
    filing = db.execute(
        select(Filing).where(Filing.id == filing_id)
    ).scalar_one_or_none()
    if filing is None:
        raise HTTPException(status_code=404, detail=f"Filing {filing_id} not found")

    company = db.execute(
        select(Company).where(Company.id == filing.company_id)
    ).scalar_one_or_none()

    ar = db.execute(
        select(AuditorReport).where(AuditorReport.filing_id == filing.id)
    ).scalar_one_or_none()

    gcf_row = db.execute(
        select(GoingConcernFlag, Filing, Company, AuditorReport)
        .join(Filing, GoingConcernFlag.filing_id == Filing.id)
        .join(Company, GoingConcernFlag.company_id == Company.id)
        .outerjoin(AuditorReport, AuditorReport.filing_id == Filing.id)
        .where(GoingConcernFlag.filing_id == filing.id)
    ).first()

    flag_resp = None
    if gcf_row:
        flag_resp = _to_flag_response(gcf_row[0], gcf_row[1], gcf_row[2],
                                       gcf_row[3].audit_firm if gcf_row[3] else None)

    return FilingResponse(
        id=filing.id,
        accession_number=filing.accession_number,
        form_type=filing.form_type,
        filing_date=filing.filing_date,
        period_of_report=filing.period_of_report,
        filing_url=filing.filing_url,
        company=CompanyBrief(
            cik=company.cik,
            ticker=company.ticker,
            name=company.name,
            display_name=getattr(company, "display_name", None),
        ),
        auditor_report_excerpt=(ar.report_text[:2000] if ar else None),
        audit_firm=(ar.audit_firm if ar else None),
        going_concern_flag=flag_resp,
    )
