"""Post-LLM validation: verify quoted language is present and compute offsets.

Validation is deliberately kept outside ClaudeClassifier so it can be unit-tested
without any API calls.  All checks run deterministically on plain strings.

Whitespace normalisation
------------------------
LLMs collapse whitespace when reproducing quoted text (e.g. multiple spaces or
line-breaks from the original SEC HTML become single spaces).  The validator
therefore attempts two matching strategies in order:

  1. Exact ``str.find()`` — fast path, works when the LLM preserved whitespace.
  2. Whitespace-normalised search via ``_find_quote_with_normalization`` — maps
     the normalised match back to original character offsets.

Hard failures only if the quote is absent under *both* strategies.
"""

from __future__ import annotations

import re

from gct.classifier.schemas import ClassifierResponse

# Regex patterns that we expect to appear in CRITICAL-severity quoted language.
# A missing match is a WARNING (not a hard failure) because the LLM may have
# caught phrasing we haven't anticipated — we log it for human review.
_CRITICAL_PHRASE = re.compile(
    r"""
    (?:
        substantial \s+ doubt .{0,100} going \s+ concern
      | going \s+ concern .{0,100} substantial \s+ doubt
    )
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

# Confidence below this is suspicious (warning, not hard failure).
_LOW_CONFIDENCE_THRESHOLD = 0.3


# ── Whitespace and typography normalisation helpers ───────────────────────────

# Map Unicode typographic characters to their ASCII counterparts.
# Each replacement is a single ASCII character so that the mapping of
# normalised-index → original-index remains 1-to-1 (no length changes).
_UNICODE_REPLACEMENTS: dict[str, str] = {
    "\u2018": "'",   # left single quotation mark
    "\u2019": "'",   # right single quotation mark / apostrophe
    "\u201c": '"',   # left double quotation mark
    "\u201d": '"',   # right double quotation mark
    "\u2013": "-",   # en dash
    "\u2014": "-",   # em dash
    "\u00a0": " ",   # non-breaking space
    "\u00d7": "x",   # multiplication sign
    "\ufffd": "?",   # replacement character (garbled encoding)
}


def _normalize_whitespace(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs in *text* to single spaces.

    Returns
    -------
    (normalized_text, original_indices)
        ``original_indices[i]`` is the index in *text* that corresponds to
        character ``i`` in *normalized_text*.  This lets callers map a match
        position in the normalised string back to the original offsets.
    """
    normalized_chars: list[str] = []
    original_indices: list[int] = []
    last_was_space = False

    for i, ch in enumerate(text):
        if ch.isspace():
            if not last_was_space:
                normalized_chars.append(" ")
                original_indices.append(i)
                last_was_space = True
        else:
            normalized_chars.append(ch)
            original_indices.append(i)
            last_was_space = False

    return "".join(normalized_chars), original_indices


def _normalize_for_search(text: str) -> tuple[str, list[int]]:
    """Full normalisation for fuzzy quote matching.

    Applies (in order):
      1. Replace common Unicode typographic characters with ASCII equivalents
         (1-to-1 replacements so original-index tracking stays valid).
      2. Collapse runs of whitespace to a single space.
      3. Convert to lower-case.

    Returns
    -------
    (normalized_text, original_indices)
        ``original_indices[i]`` gives the index in the *original* text for
        character ``i`` of the normalised string.
    """
    # Step 1: replace typographic characters (1-to-1)
    chars: list[str] = []
    orig: list[int] = []
    for i, ch in enumerate(text):
        replacement = _UNICODE_REPLACEMENTS.get(ch)
        chars.append(replacement if replacement is not None else ch)
        orig.append(i)

    # Step 2: collapse whitespace
    norm_chars: list[str] = []
    norm_orig: list[int] = []
    last_was_space = False
    for ch, o in zip(chars, orig):
        if ch.isspace():
            if not last_was_space:
                norm_chars.append(" ")
                norm_orig.append(o)
                last_was_space = True
        else:
            # Step 3: lowercase
            norm_chars.append(ch.lower())
            norm_orig.append(o)
            last_was_space = False

    return "".join(norm_chars), norm_orig


def _find_quote_with_normalization(
    quote: str, source: str
) -> tuple[int, int] | None:
    """Find *quote* inside *source*, ignoring whitespace and typography differences.

    The search is performed on versions of both strings that have had:
      - Unicode typographic characters replaced with ASCII equivalents
      - whitespace runs collapsed to a single space
      - text lower-cased

    On success, the returned offsets refer to *source* (the original,
    un-normalised string).

    Returns
    -------
    (original_start, original_end) or ``None`` if the quote is not found.
    """
    norm_quote, _ = _normalize_for_search(quote)
    norm_source, original_indices = _normalize_for_search(source)

    norm_idx = norm_source.find(norm_quote)
    if norm_idx == -1:
        return None

    original_start = original_indices[norm_idx]
    original_end = original_indices[norm_idx + len(norm_quote) - 1] + 1
    return original_start, original_end


# ── Main validator ────────────────────────────────────────────────────────────


def validate_classification(
    response: ClassifierResponse,
    report_text: str,
) -> tuple[bool, list[str], int | None, int | None]:
    """Validate a ClassifierResponse against the original report text.

    Rules
    -----
    Hard failures (is_valid=False):
      1. severity == "none" but quoted_language is non-empty → fail.
      2. severity != "none" but quoted_language is empty → fail.
      3. severity != "none" and quoted_language is not found in report_text,
         even after whitespace normalisation → fail.

    Warnings (appended to errors list but is_valid stays True):
      4. classification_confidence < 0.3 → "very low confidence".
      5. severity == "critical" but quoted_language lacks expected phrase pattern
         → "severity critical but quote lacks expected phrase".

    Returns
    -------
    (is_valid, errors, char_offset_start, char_offset_end)
    """
    errors: list[str] = []
    char_offset_start: int | None = None
    char_offset_end: int | None = None

    # ── Rule 1: severity "none" must have null/empty quoted_language ─────────
    if response.severity == "none":
        if response.quoted_language and response.quoted_language.strip():
            errors.append(
                "severity is 'none' but quoted_language is non-empty; "
                "set quoted_language to null when no flag is present"
            )
            return False, errors, None, None
        return True, errors, None, None

    # ── Rules 2-5 apply when severity != "none" ──────────────────────────────

    # Rule 2: quoted_language must be non-empty
    quote = response.quoted_language or ""
    if not quote.strip():
        errors.append(
            f"severity is '{response.severity}' but quoted_language is empty; "
            "must provide the exact verbatim sentence(s) from the report"
        )
        return False, errors, None, None

    # Rule 3: find quote in report_text (exact first, then whitespace-normalised)
    idx = report_text.find(quote)
    if idx != -1:
        # Exact match — fast path
        char_offset_start = idx
        char_offset_end = idx + len(quote)
    else:
        # Try whitespace-normalised search to handle LLM whitespace collapsing
        result = _find_quote_with_normalization(quote, report_text)
        if result is None:
            errors.append(
                "quoted_language not found in report_text after whitespace normalization; "
                "the quote must be a verbatim (or whitespace-equivalent) substring of the auditor report"
            )
            return False, errors, None, None
        char_offset_start, char_offset_end = result

    # Rule 4: very low confidence warning
    if response.classification_confidence < _LOW_CONFIDENCE_THRESHOLD:
        errors.append(
            f"very low confidence ({response.classification_confidence:.2f}); "
            "manual review recommended"
        )

    # Rule 5: critical severity should contain expected phrase pattern
    if response.severity == "critical" and not _CRITICAL_PHRASE.search(quote):
        errors.append(
            "severity critical but quote lacks expected phrase "
            "('substantial doubt … going concern' or vice versa); "
            "verify this is a genuine PCAOB AS 2415 opinion modifier"
        )

    return True, errors, char_offset_start, char_offset_end
