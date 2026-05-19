"""Tests for classifier/validator.py — post-LLM validation logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gct.classifier.schemas import ClassifierResponse
from gct.classifier.validator import validate_classification, _find_quote_with_normalization

FIXTURES = Path(__file__).parent / "fixtures" / "classifier_responses"


def _load_response(name: str) -> ClassifierResponse:
    data = json.loads((FIXTURES / name).read_text())
    return ClassifierResponse(**data)


# ── Helper report texts that embed the fixture quoted_language ────────────────

_CRITICAL_REPORT = (
    "Report of Independent Registered Public Accounting Firm\n"
    "To the Stockholders and Board of Directors of XYZ Corp.\n"
    "The accompanying financial statements have been prepared assuming the Company "
    "will continue as a going concern. As discussed in Note 2 to the financial "
    "statements, the Company has suffered recurring losses from operations and has "
    "a net capital deficiency that raise substantial doubt about its ability to "
    "continue as a going concern.\n"
    "/s/ Ernst & Young LLP\nNew York, NY\nMarch 10, 2023"
)

_ELEVATED_REPORT = (
    "Report of Independent Registered Public Accounting Firm\n"
    "To the Shareholders of ABC Inc.\n"
    "These conditions raise substantial doubt about the Company's ability to continue "
    "as a going concern. However, management has implemented a plan to alleviate the "
    "substantial doubt by raising additional capital through a private placement offering "
    "and reducing operating expenses.\n"
    "/s/ Deloitte & Touche LLP\nChicago, IL\nApril 5, 2023"
)

_WATCH_REPORT = (
    "Report of Independent Registered Public Accounting Firm\n"
    "To the Board of Directors of MNO Inc.\n"
    "Our audit procedures included assessing the appropriateness of the going concern "
    "basis of accounting used by management and, based on the audit evidence obtained, "
    "we have concluded that a material uncertainty exists that may cast significant doubt "
    "on the Company's ability to continue as a going concern.\n"
    "/s/ KPMG LLP\nBoston, MA\nFebruary 28, 2023"
)

_CLEAN_REPORT = (
    "Report of Independent Registered Public Accounting Firm\n"
    "To the Stockholders and Board of Directors of BIG Corp.\n"
    "In our opinion, the consolidated financial statements present fairly, in all material "
    "respects, the financial position of BIG Corp. We conducted our audit in accordance "
    "with the standards of the PCAOB.\n"
    "/s/ PricewaterhouseCoopers LLP\nSan Jose, CA\nOctober 28, 2023"
)


# ── test_quote_present_returns_correct_offsets ────────────────────────────────


def test_quote_present_returns_correct_offsets() -> None:
    response = _load_response("critical_going_concern.json")
    is_valid, errors, start, end = validate_classification(response, _CRITICAL_REPORT)

    assert is_valid, f"Expected valid; errors: {errors}"
    assert start is not None and end is not None
    assert start >= 0
    assert end > start
    # The quote must be exactly at the reported offsets
    assert _CRITICAL_REPORT[start:end] == response.quoted_language


def test_quote_present_elevated_offsets() -> None:
    response = _load_response("elevated_doubt_with_mitigation.json")
    is_valid, errors, start, end = validate_classification(response, _ELEVATED_REPORT)

    assert is_valid, f"Expected valid; errors: {errors}"
    assert start is not None
    assert _ELEVATED_REPORT[start:end] == response.quoted_language


# ── test_quote_absent_fails_validation ───────────────────────────────────────


def test_quote_absent_fails_validation() -> None:
    response = ClassifierResponse(
        has_going_concern_language=True,
        severity="critical",
        quoted_language="This exact phrase does not appear in the report text anywhere.",
        classification_confidence=0.95,
        reasoning="Hallucinated quote.",
    )
    is_valid, errors, start, end = validate_classification(response, _CLEAN_REPORT)

    assert not is_valid
    # Accept both the old "not present" phrasing and the new "not found" phrasing
    assert any("not" in e and ("found" in e or "present" in e) for e in errors)
    assert start is None
    assert end is None


# ── test_none_severity_requires_null_quote ───────────────────────────────────


def test_none_severity_with_null_quote_passes() -> None:
    response = _load_response("no_going_concern.json")
    is_valid, errors, start, end = validate_classification(response, _CLEAN_REPORT)

    assert is_valid
    assert start is None
    assert end is None


def test_none_severity_with_non_empty_quote_fails() -> None:
    response = ClassifierResponse(
        has_going_concern_language=False,
        severity="none",
        quoted_language="Some text that shouldn't be here.",
        classification_confidence=0.99,
        reasoning="Clean opinion.",
    )
    is_valid, errors, start, end = validate_classification(response, _CLEAN_REPORT)

    assert not is_valid
    assert any("none" in e and "non-empty" in e for e in errors)


# ── test_critical_without_expected_phrase_warns_but_passes ───────────────────


def test_critical_without_expected_phrase_warns_but_passes() -> None:
    """Critical severity where the quote exists in the text but lacks the
    'substantial doubt ... going concern' regex — should warn but not fail."""
    report = "To the Shareholders.\nThe Company has a material weakness.\nSome text here. " + "x" * 300
    suspicious_quote = "The Company has a material weakness."
    report_with_quote = report  # quote IS in the report

    response = ClassifierResponse(
        has_going_concern_language=True,
        severity="critical",
        quoted_language=suspicious_quote,
        classification_confidence=0.85,
        reasoning="Flagged as critical but lacks canonical phrase.",
    )
    is_valid, errors, start, end = validate_classification(response, report_with_quote)

    assert is_valid, f"Expected valid (just a warning); errors: {errors}"
    assert any("critical" in e and "lacks" in e for e in errors)
    assert start is not None


# ── test_low_confidence_warns_but_passes ─────────────────────────────────────


def test_low_confidence_warns_but_passes() -> None:
    """Very low confidence (<0.3) should append a warning but not fail validation."""
    response = ClassifierResponse(
        has_going_concern_language=True,
        severity="elevated",
        quoted_language=_ELEVATED_REPORT[50:120],  # take a slice as the quote
        classification_confidence=0.20,  # below LOW_CONFIDENCE_THRESHOLD
        reasoning="Uncertain.",
    )

    # Find a slice that actually exists in the report
    quote = _ELEVATED_REPORT[50:120]
    response = ClassifierResponse(
        has_going_concern_language=True,
        severity="elevated",
        quoted_language=quote,
        classification_confidence=0.20,
        reasoning="Uncertain.",
    )
    is_valid, errors, start, end = validate_classification(response, _ELEVATED_REPORT)

    assert is_valid
    assert any("very low confidence" in e for e in errors)
    assert start is not None


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_string_quote_on_non_none_severity_fails() -> None:
    response = ClassifierResponse(
        has_going_concern_language=True,
        severity="watch",
        quoted_language="",  # empty — should fail
        classification_confidence=0.75,
        reasoning="Watch tier.",
    )
    is_valid, errors, start, end = validate_classification(response, _WATCH_REPORT)

    assert not is_valid
    assert any("empty" in e for e in errors)


def test_watch_severity_with_valid_quote_passes() -> None:
    response = _load_response("watch_mda_only.json")
    is_valid, errors, start, end = validate_classification(response, _WATCH_REPORT)

    assert is_valid, f"Expected valid; errors: {errors}"
    assert start is not None
    assert _WATCH_REPORT[start:end] == response.quoted_language


# ── Whitespace-normalisation tests ────────────────────────────────────────────
# These cover the case where the LLM collapses whitespace when reproducing a
# quote from a source text that has newlines / multiple spaces from HTML formatting.

_MULTISPACE_REPORT = (
    "Report of Independent Registered Public Accounting Firm\n"
    "To the Shareholders.\n"
    "These  conditions   raise  substantial  doubt about the Company's ability "
    "to continue as a going concern.\n"
    "/s/ Ernst & Young LLP\nNew York, NY\nMarch 10, 2023"
)

_NEWLINE_REPORT = (
    "Report of Independent Registered Public Accounting Firm\n"
    "To the Shareholders.\n"
    "These conditions raise\n"
    "substantial doubt about\n"
    "the Company's ability to continue as a going concern.\n"
    "/s/ Ernst & Young LLP\nNew York, NY\nMarch 10, 2023"
)


def test_finds_quote_with_collapsed_whitespace() -> None:
    """Validator succeeds when LLM collapses multiple spaces to one."""
    llm_quote = "These conditions raise substantial doubt about the Company's ability to continue as a going concern."
    # The source has multiple spaces between words
    response = ClassifierResponse(
        has_going_concern_language=True,
        severity="critical",
        quoted_language=llm_quote,
        classification_confidence=0.95,
        reasoning="Going concern.",
    )
    is_valid, errors, start, end = validate_classification(response, _MULTISPACE_REPORT)

    assert is_valid, f"Expected valid after normalisation; errors: {errors}"
    assert start is not None and end is not None
    assert start > 0  # not the 0-0 default


def test_finds_quote_with_newlines_in_source() -> None:
    """Validator succeeds when the source has mid-phrase newlines the LLM collapsed."""
    llm_quote = "These conditions raise substantial doubt about the Company's ability to continue as a going concern."
    response = ClassifierResponse(
        has_going_concern_language=True,
        severity="critical",
        quoted_language=llm_quote,
        classification_confidence=0.95,
        reasoning="Going concern.",
    )
    is_valid, errors, start, end = validate_classification(response, _NEWLINE_REPORT)

    assert is_valid, f"Expected valid after normalisation; errors: {errors}"
    assert start is not None and end is not None
    assert start > 0


def test_finds_quote_with_multiple_spaces() -> None:
    """_find_quote_with_normalization helper: multiple-space collapse."""
    source = "The Company has   suffered   recurring   losses."
    quote = "The Company has suffered recurring losses."
    result = _find_quote_with_normalization(quote, source)

    assert result is not None
    start, end = result
    # The original-text substring at [start:end] should, when whitespace-normalised,
    # equal the normalised quote
    import re
    original_slice = source[start:end]
    assert " ".join(quote.split()) == " ".join(original_slice.split())


def test_quote_truly_absent_returns_none() -> None:
    """_find_quote_with_normalization returns None for a truly absent phrase."""
    source = "This is a clean audit opinion with no going-concern language."
    quote = "substantial doubt about the Company's ability to continue as a going concern"
    result = _find_quote_with_normalization(quote, source)

    assert result is None


def test_offset_mapping_is_correct_after_normalization() -> None:
    """Offsets returned by the normalised search round-trip back to the original text."""
    source = "Opinion:\nThese\n  conditions raise substantial\ndoubt.\nEnd."
    # LLM collapses it to a single-space string
    quote = "These conditions raise substantial doubt."
    result = _find_quote_with_normalization(quote, source)

    assert result is not None, "Expected to find the quote"
    start, end = result
    # Verify: the slice in the original source, when whitespace-normalised, equals the quote
    original_slice = source[start:end]
    assert " ".join(original_slice.split()) == " ".join(quote.split())
