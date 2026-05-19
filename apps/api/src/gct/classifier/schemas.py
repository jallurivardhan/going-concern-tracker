"""Pydantic models for the Tier-2 classification layer.

Three distinct model levels:
    ClassifierInput    — validated input passed to the LLM prompt
    ClassifierResponse — structured output returned by Claude (Instructor-enforced)
    ClassificationResult — final result after validation and offset computation
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ClassifierInput(BaseModel):
    """Input to the LLM.  Validated before the prompt is assembled."""

    report_text: str = Field(..., min_length=200, max_length=100_000)
    company_name: str
    filing_form_type: str  # "10-K"
    filing_date: date


class ClassifierResponse(BaseModel):
    """Required structured output from Claude.  Instructor enforces this schema.

    Every field is validated by Instructor before the caller receives the object;
    if validation fails, Instructor retries up to max_retries times.
    """

    has_going_concern_language: bool = Field(
        ...,
        description=(
            "True if the auditor's report contains substantial-doubt-about-going-concern language."
        ),
    )
    severity: Literal["critical", "elevated", "watch", "none"] = Field(
        ...,
        description=(
            "critical: Auditor formally issued going-concern opinion with no mitigating language. "
            "elevated: Auditor noted conditions raising substantial doubt, but management's plans alleviate it. "
            "watch: Going-concern risk discussed in MD&A or risk factors only, no formal audit opinion modifier. "
            "none: No going-concern language present."
        ),
    )
    quoted_language: str | None = Field(
        None,
        description=(
            "The EXACT verbatim sentence(s) from the auditor's report that triggered this classification. "
            "Must be a contiguous substring of the report. Empty string if severity is 'none'."
        ),
    )
    classification_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Self-reported confidence in this classification on a 0.0-1.0 scale.",
    )
    reasoning: str = Field(
        ...,
        max_length=500,
        description=(
            "A brief explanation of why this classification was chosen, for audit purposes."
        ),
    )


class ClassificationResult(BaseModel):
    """Final classifier output after validation and offset computation.

    This is the record written to the going_concern_flags table.
    """

    auditor_report_id: uuid.UUID
    has_going_concern: bool
    severity: Literal["critical", "elevated", "watch", "none"]
    flag_type: Literal["new", "continuing", "resolved", "none"]
    quoted_language: str | None
    char_offset_start: int | None
    char_offset_end: int | None
    # Accepted as float from LLM; stored as Decimal in DB.
    classification_confidence: Decimal
    classifier_version: str
    model_used: str
    reasoning: str
    validation_passed: bool
    validation_errors: list[str] = Field(default_factory=list)
    trace_url: str | None = None
