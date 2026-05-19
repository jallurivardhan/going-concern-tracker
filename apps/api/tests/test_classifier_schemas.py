"""Tests for classifier/schemas.py — Pydantic model validation."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from gct.classifier.schemas import ClassificationResult, ClassifierInput, ClassifierResponse

FIXTURES = Path(__file__).parent / "fixtures" / "classifier_responses"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ── ClassifierResponse ────────────────────────────────────────────────────────


def test_response_accepts_valid_critical_classification() -> None:
    data = _load_fixture("critical_going_concern.json")
    resp = ClassifierResponse(**data)
    assert resp.severity == "critical"
    assert resp.has_going_concern_language is True
    assert resp.quoted_language is not None
    assert 0.0 <= resp.classification_confidence <= 1.0


def test_response_accepts_valid_elevated_classification() -> None:
    data = _load_fixture("elevated_doubt_with_mitigation.json")
    resp = ClassifierResponse(**data)
    assert resp.severity == "elevated"
    assert resp.has_going_concern_language is True


def test_response_accepts_none_with_null_quote() -> None:
    data = _load_fixture("no_going_concern.json")
    resp = ClassifierResponse(**data)
    assert resp.severity == "none"
    assert resp.has_going_concern_language is False
    assert resp.quoted_language is None


def test_response_rejects_invalid_severity_value() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ClassifierResponse(
            has_going_concern_language=True,
            severity="high",  # not a valid Literal
            quoted_language="some text",
            classification_confidence=0.9,
            reasoning="test",
        )
    assert "severity" in str(exc_info.value).lower()


def test_response_rejects_confidence_above_1() -> None:
    with pytest.raises(ValidationError):
        ClassifierResponse(
            has_going_concern_language=False,
            severity="none",
            quoted_language=None,
            classification_confidence=1.5,  # above le=1.0
            reasoning="test",
        )


def test_response_rejects_confidence_below_0() -> None:
    with pytest.raises(ValidationError):
        ClassifierResponse(
            has_going_concern_language=True,
            severity="critical",
            quoted_language="some text",
            classification_confidence=-0.1,  # below ge=0.0
            reasoning="test",
        )


def test_response_rejects_reasoning_too_long() -> None:
    with pytest.raises(ValidationError):
        ClassifierResponse(
            has_going_concern_language=False,
            severity="none",
            quoted_language=None,
            classification_confidence=0.99,
            reasoning="x" * 501,  # max_length=500
        )


# ── ClassifierInput ───────────────────────────────────────────────────────────


def test_input_rejects_short_report_text() -> None:
    with pytest.raises(ValidationError):
        ClassifierInput(
            report_text="short",  # min_length=200
            company_name="Acme Corp",
            filing_form_type="10-K",
            filing_date=date(2023, 12, 31),
        )


def test_input_accepts_valid_input() -> None:
    ci = ClassifierInput(
        report_text="x" * 200,
        company_name="Acme Corp",
        filing_form_type="10-K",
        filing_date=date(2023, 12, 31),
    )
    assert ci.filing_form_type == "10-K"


# ── ClassificationResult ──────────────────────────────────────────────────────


def test_classification_result_stores_decimal_confidence() -> None:
    result = ClassificationResult(
        auditor_report_id=uuid.uuid4(),
        has_going_concern=False,
        severity="none",
        flag_type="none",
        quoted_language=None,
        char_offset_start=None,
        char_offset_end=None,
        classification_confidence=Decimal("0.990"),
        classifier_version="v1.0-claude",
        model_used="claude-haiku-4-5",
        reasoning="Clean opinion.",
        validation_passed=True,
    )
    assert isinstance(result.classification_confidence, Decimal)
    assert result.validation_errors == []


def test_classification_result_rejects_invalid_flag_type() -> None:
    with pytest.raises(ValidationError):
        ClassificationResult(
            auditor_report_id=uuid.uuid4(),
            has_going_concern=True,
            severity="critical",
            flag_type="unknown_type",  # not a valid Literal
            quoted_language="some text",
            char_offset_start=0,
            char_offset_end=9,
            classification_confidence=Decimal("0.95"),
            classifier_version="v1.0-claude-haiku-4-5",
            model_used="claude-haiku-4-5",
            reasoning="Going concern.",
            validation_passed=True,
        )


def test_classifier_version_format_no_double_claude() -> None:
    """CLASSIFIER_VERSION must not already contain 'claude'; the model name is appended at runtime.

    The bug was CLASSIFIER_VERSION = 'v1.0-claude' combined with
    f'{CLASSIFIER_VERSION}-{model_name}' where model_name = 'claude-haiku-4-5',
    producing 'v1.0-claude-claude-haiku-4-5'.
    The fix: CLASSIFIER_VERSION = 'v1.0'.
    """
    from gct.classifier.prompts import CLASSIFIER_VERSION

    # The constant itself must not embed the model name
    assert "claude" not in CLASSIFIER_VERSION, (
        f"CLASSIFIER_VERSION should not contain 'claude'; got {CLASSIFIER_VERSION!r}"
    )

    # Simulate what classifier.py does when combining with a model name
    for model in ("claude-haiku-4-5", "claude-sonnet-4-5"):
        combined = f"{CLASSIFIER_VERSION}-{model}"
        # Must not double 'claude'
        assert "claude-claude" not in combined, (
            f"Double 'claude' in combined version: {combined!r}"
        )
        # Must match expected pattern
        assert combined == f"v1.0-{model}", f"Unexpected format: {combined!r}"
