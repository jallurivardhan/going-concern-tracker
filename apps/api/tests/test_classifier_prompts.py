"""Tests for classifier/prompts.py — version and template correctness."""

from __future__ import annotations

from datetime import date

from gct.classifier.prompts import (
    CLASSIFIER_VERSION,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)


def test_classifier_version_is_set() -> None:
    assert CLASSIFIER_VERSION
    assert isinstance(CLASSIFIER_VERSION, str)
    # The constant is the base version (e.g. "v1.0"); the model name is appended
    # at runtime in classifier.py: f"{CLASSIFIER_VERSION}-{model_used}".
    # The constant must NOT embed the model name to avoid double-prefixing.
    assert CLASSIFIER_VERSION.startswith("v")
    assert "claude-claude" not in CLASSIFIER_VERSION  # guard against regression


def test_system_prompt_includes_all_severity_tiers() -> None:
    for tier in ("CRITICAL", "ELEVATED", "WATCH", "NONE"):
        assert tier in SYSTEM_PROMPT, f"Expected severity tier '{tier}' in SYSTEM_PROMPT"


def test_system_prompt_includes_pcaob_reference() -> None:
    assert "PCAOB" in SYSTEM_PROMPT, "SYSTEM_PROMPT should reference PCAOB AS 2415"


def test_system_prompt_includes_verbatim_rule() -> None:
    assert "verbatim" in SYSTEM_PROMPT.lower(), (
        "SYSTEM_PROMPT must instruct the LLM to quote language verbatim"
    )


def test_system_prompt_includes_boilerplate_warning() -> None:
    # Prompt must warn that the going-concern basis phrase alone is NOT a flag
    assert "going concern basis" in SYSTEM_PROMPT.lower()


def test_user_prompt_template_substitutes_correctly() -> None:
    filled = USER_PROMPT_TEMPLATE.format(
        company_name="Test Corp",
        filing_form_type="10-K",
        filing_date=date(2023, 12, 31),
        report_text="We have audited the accompanying financial statements.",
    )
    assert "Test Corp" in filled
    assert "10-K" in filled
    assert "2023-12-31" in filled
    assert "We have audited" in filled


def test_user_prompt_template_has_all_placeholders() -> None:
    for placeholder in ("{company_name}", "{filing_form_type}", "{filing_date}", "{report_text}"):
        assert placeholder in USER_PROMPT_TEMPLATE, (
            f"USER_PROMPT_TEMPLATE missing placeholder: {placeholder}"
        )
