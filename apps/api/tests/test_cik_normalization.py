"""Tests for normalize_cik() in gct.ingestion."""

import pytest
from gct.ingestion import normalize_cik


def test_pads_short_cik() -> None:
    assert normalize_cik("886158") == "0000886158"


def test_already_padded_unchanged() -> None:
    assert normalize_cik("0000886158") == "0000886158"


def test_strips_cik_prefix() -> None:
    assert normalize_cik("CIK886158") == "0000886158"


def test_strips_cik_prefix_with_padding() -> None:
    assert normalize_cik("CIK0000886158") == "0000886158"


def test_strips_whitespace() -> None:
    assert normalize_cik("  886158  ") == "0000886158"


def test_rejects_non_numeric() -> None:
    with pytest.raises(ValueError, match="Invalid CIK"):
        normalize_cik("abc")


def test_rejects_empty_string() -> None:
    with pytest.raises(ValueError, match="Invalid CIK"):
        normalize_cik("")


def test_handles_all_zeros() -> None:
    assert normalize_cik("0000000000") == "0000000000"
