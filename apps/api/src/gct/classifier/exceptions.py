"""Exceptions for the Tier-2 classification layer."""

from __future__ import annotations


class ClassificationError(Exception):
    """Base exception for all classifier errors."""


class ValidationError(ClassificationError):
    """The LLM response failed post-LLM validation (e.g., quote not in report)."""


class MaxRetriesExceededError(ClassificationError):
    """Instructor could not produce a valid Pydantic response after max_retries attempts."""
