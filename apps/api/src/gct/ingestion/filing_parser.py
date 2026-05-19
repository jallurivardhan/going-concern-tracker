"""Deterministic auditor-report extractor for SEC 10-K filings.

This is a Tier-1 component: no LLM calls, no probabilistic inference.
The extraction relies entirely on the structural conventions that auditors
and their legal teams follow when preparing EDGAR submissions:

  1. A heading that matches one of the recognised auditor-report patterns.
  2. Classification of the 200 chars after the heading as either a TOC entry
     (skipped) or the real report body (extracted).
  3. Section end located via the next financial-statement heading, a signature
     block, or a fixed length cap as a last resort.

Heading classification uses two signal sets:
  - TOC indicators: standalone page numbers (e.g. "57") or section-name lines
    like "Consolidated Balance Sheets" immediately following the heading.
  - Real-report indicators: "To the Stockholders", "We have audited", etc.

Known limitations:
  - Some older XBRL-embedded filings render headings as plain text inside
    tables; BeautifulSoup's get_text() still captures them, but whitespace
    normalisation may be imperfect.
  - 10-Q filings do not include a formal auditor opinion; this function returns
    None for 10-Q inputs.  MD&A going-concern disclosures are handled separately.

Raw HTML is stored at ingestion time (see persistence.py) so that extraction
can be re-run against the same source document without a second SEC request.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Compiled patterns ───────────────────────────────────────────────────────

# Primary heading patterns for the auditor's report section (case-insensitive).
# Order matters: more specific patterns first.
_AUDIT_HEADINGS = re.compile(
    r"""
    (?:
        REPORT \s+ OF \s+ INDEPENDENT \s+ REGISTERED \s+ PUBLIC \s+ ACCOUNTING \s+ FIRM
      | REPORT \s+ OF \s+ INDEPENDENT \s+ REGISTERED \s+ PUBLIC \s+ ACCOUNTANTS?
      | INDEPENDENT \s+ AUDITORS?['\u2019]? \s+ REPORT
      | INDEPENDENT \s+ AUDITOR['\u2019]S \s+ REPORT
      | REPORT \s+ OF \s+ INDEPENDENT \s+ AUDITORS?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Headings that mark the start of the next major section (end of auditor report).
_FINANCIAL_STATEMENT_HEADINGS = re.compile(
    r"""
    (?:
        CONSOLIDATED \s+ BALANCE \s+ SHEETS?
      | CONSOLIDATED \s+ STATEMENTS? \s+ OF \s+ (?:OPERATIONS|INCOME|COMPREHENSIVE|CASH|EARNINGS)
      | COMBINED \s+ STATEMENTS? \s+ OF
      | BALANCE \s+ SHEETS? \s* \(
      | STATEMENTS? \s+ OF \s+ OPERATIONS?
      | STATEMENTS? \s+ OF \s+ INCOME
      | NOTES \s+ TO \s+ (?:CONSOLIDATED \s+)? FINANCIAL \s+ STATEMENTS?
      | SELECTED \s+ FINANCIAL \s+ DATA
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Signature block: "/s/ SomeFirmName"
_SIGNATURE = re.compile(r"/s/\s+\w", re.IGNORECASE)

# Date line: "City, ST Month DD, YYYY" or just "Month DD, YYYY"
_DATE_LINE = re.compile(
    r"""
    (?:[A-Za-z ]+,\s+[A-Za-z]{2}\s+)?
    (?:January|February|March|April|May|June|
       July|August|September|October|November|December)
    \s+ \d{1,2} ,? \s+ \d{4}
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Recognised audit firm names, ordered from most specific to generic fallback.
_AUDIT_FIRMS = re.compile(
    r"""
    (?:
        Deloitte \s* & \s* Touche (?:\s+ LLP)?
      | Ernst \s* & \s* Young (?:\s+ LLP)?
      | PricewaterhouseCoopers (?:\s+ LLP)?
      | KPMG (?:\s+ LLP)?
      | BDO \s+ USA (?:[,\s]+ LLP)?
      | Grant \s+ Thornton (?:\s+ LLP)?
      | RSM \s+ US (?:\s+ LLP)?
      | Crowe (?:\s+ LLP)?
      | Marcum (?:\s+ LLP)?
      | MaloneBailey (?:[,\s]+ LLP)?
      | Mazars \s+ USA (?:[,\s]+ LLP)?
      | [A-Z][a-zA-Z]+ \s+ [A-Z][a-zA-Z]+ \s+ LLP   # generic "{Word} {Word} LLP"
    )
    """,
    re.VERBOSE,
)

# ── Context-window classifiers (applied to the 200 chars after each heading) ─

# Signals that the heading is a table-of-contents entry, not the real section.
#
# Two types of signals:
#   1. A standalone page number on its own line (e.g. "57" or "F-4").
#   2. A financial-statement section name that is the *first thing on a line*
#      (anchored with ^ + MULTILINE).
#
# The line-start anchor is essential: "consolidated balance sheets" appears
# mid-sentence in the actual auditor report ("We have audited the accompanying
# consolidated balance sheets of…") and must NOT be treated as a TOC entry.
# In a real TOC, the section name stands alone at the start of its own line.
_TOC_INDICATOR = re.compile(
    r"""
    (?:
        ^ \s* \d{1,3} \s* $                                       # standalone page number
      | ^ \s* Consolidated \s+ Balance \s+ Sheets?                # line-start: balance sheets
      | ^ \s* Consolidated \s+ Statements? \s+ of                 # line-start: statements
      | ^ \s* Notes \s+ to \s+ (?:Consolidated \s+)? Financial    # line-start: notes
      | ^ \s* Selected \s+ Financial \s+ Data                     # line-start: selected data
      | ^ \s* Management['\u2019]?s? \s+ Discussion \s+ and       # line-start: MD&A
    )
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)

# Signals that the heading is followed by the genuine auditor report body.
_REAL_REPORT_INDICATOR = re.compile(
    r"""
    (?:
        To \s+ the \s+ (?:Stockholders?|Board \s+ of \s+ Directors?|Shareholders?)
      | We \s+ have \s+ audited
      | In \s+ our \s+ opinion
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Signals that the heading introduces only the ICFR (Internal Control over
# Financial Reporting) audit report, not the financial-statements opinion.
# When this matches the preview and the preview does NOT contain the financial-
# statements counterpart, the heading is skipped so we proceed to the next match.
_ICFR_INDICATOR = re.compile(
    r"Opinion \s+ on \s+ Internal \s+ Control \s+ Over \s+ Financial \s+ Reporting",
    re.IGNORECASE | re.VERBOSE,
)

# When the preview also includes the financial-statements opinion, the same
# report section covers both (combined report) and should NOT be skipped.
_FINANCIAL_STATEMENTS_OPINION = re.compile(
    r"Opinion \s+ on \s+ (?:the \s+)? Financial \s+ Statements",
    re.IGNORECASE | re.VERBOSE,
)

# Emphasis-of-matter / Going-Concern section headings that may appear AFTER the
# auditor's signature block but still belong to the auditor's report.
# Matching any of these causes the parser to extend the extraction window.
_EMPHASIS_OF_MATTER = re.compile(
    r"""
    (?:
        Emphasis \s+ of \s+ Matter
      | Material \s+ Uncertainty .{0,60} Going \s+ Concern
      | Substantial \s+ Doubt .{0,60} Ability \s+ to \s+ Continue
      | Going \s+ Concern \s* \n        # "Going Concern" as its own line / heading
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# How far (in chars) after the first signature block to look for an
# emphasis-of-matter section that still belongs to the auditor's report.
_EMPHASIS_LOOKAHEAD_CHARS = 5000

# Number of chars after a heading to inspect for TOC vs real-report signals.
_PREVIEW_CHARS = 200

# Minimum number of characters in a report section for the result to be returned.
_MIN_REPORT_CHARS = 200

# If an extracted report exceeds this many characters the parser looks for a
# signature/date boundary at which to truncate.  Reports longer than this are
# almost certainly over-extracting into financial-statement data.
_MAX_REPORT_CHARS = 30_000


class AuditorReportExtraction(BaseModel):
    """Structured result of extracting the auditor's report from a 10-K HTML filing."""

    report_text: str
    """The extracted auditor's report text (UTF-8 string)."""

    audit_firm: str | None
    """The identified audit firm name, or None if not deterministically found."""

    extraction_method: str
    """One of:
    - "heading_match_v1"          — end found via financial-statement heading; real-report confirmed.
    - "heading_match_v2_fallback" — end found via signature/date; real-report confirmed.
    - "heading_match_v2_ambiguous"— neither TOC nor real-report indicators matched; used with caution.
    """

    char_offset_start: int
    """Character offset of the heading in the cleaned text representation."""

    char_offset_end: int
    """Character offset of the end of the report in the cleaned text representation."""

    confidence: str
    """Extraction confidence: "high" | "medium" | "low"."""


def extract_auditor_report(
    filing_html: str,
    form_type: str,
    filing_id: str = "<unknown>",
) -> AuditorReportExtraction | None:
    """Locate and extract the auditor's report from a 10-K HTML filing.

    Args:
        filing_html: Raw HTML of the primary filing document.
        form_type: e.g. "10-K".  Returns None immediately for 10-Q.
        filing_id: Accession number or identifier used only in log messages.

    Returns:
        ``AuditorReportExtraction`` on success, ``None`` if no report found.
    """
    # 10-Q filings do not contain a formal auditor opinion.
    if form_type.upper().startswith("10-Q"):
        return None

    # ── 1. Parse HTML → clean plain text ────────────────────────────────────
    soup = BeautifulSoup(filing_html, "lxml")
    text = _html_to_clean_text(soup)

    # ── 2. Walk heading matches; classify each as TOC entry or real report ───
    for heading_match in _AUDIT_HEADINGS.finditer(text):
        report_start = heading_match.start()
        search_from = heading_match.end()

        # Inspect the first _PREVIEW_CHARS chars after the heading.
        preview = text[search_from : search_from + _PREVIEW_CHARS]

        # ── TOC false-positive guard ─────────────────────────────────────
        # If a standalone page number or a financial-statement section name
        # appears immediately after the heading, this is a TOC entry — skip it.
        if _TOC_INDICATOR.search(preview):
            logger.debug(
                "Skipping TOC-like audit heading at offset %d in filing %s",
                report_start,
                filing_id,
            )
            continue

        # ── ICFR-only guard ──────────────────────────────────────────────
        # Some 10-Ks carry TWO separate audit reports: one on Internal Controls
        # (ICFR) and one on the Financial Statements.  The ICFR report does not
        # contain going-concern language; prefer the financial-statements report.
        # Skip a heading whose preview announces ONLY the ICFR opinion.
        if _ICFR_INDICATOR.search(preview) and not _FINANCIAL_STATEMENTS_OPINION.search(preview):
            logger.debug(
                "Skipping ICFR-only audit heading at offset %d in filing %s",
                report_start,
                filing_id,
            )
            continue

        # ── Confirm it's the real report body ────────────────────────────
        is_confirmed_real = bool(_REAL_REPORT_INDICATOR.search(preview))

        # ── 3. Find end of report ────────────────────────────────────────
        end_match = _FINANCIAL_STATEMENT_HEADINGS.search(text, search_from)

        if end_match and (end_match.start() - search_from) > _MIN_REPORT_CHARS:
            report_end = end_match.start()
            if is_confirmed_real:
                extraction_method = "heading_match_v1"
                confidence = "high"
            else:
                extraction_method = "heading_match_v2_ambiguous"
                confidence = "low"
        else:
            # Fallback: find signature block (/s/ ...) then extend for date.
            sig_match = _SIGNATURE.search(text, search_from)
            if sig_match:
                # After the first signature, look ahead for an Emphasis-of-Matter
                # section that is still part of the auditor's report.
                emphasis_region_start = sig_match.end()
                emphasis_region_end = min(
                    emphasis_region_start + _EMPHASIS_LOOKAHEAD_CHARS, len(text)
                )
                emphasis_region = text[emphasis_region_start:emphasis_region_end]
                emphasis_match = _EMPHASIS_OF_MATTER.search(emphasis_region)

                if emphasis_match:
                    # Extend to the next signature/financial-heading AFTER the
                    # emphasis section.
                    emphasis_abs_start = emphasis_region_start + emphasis_match.start()
                    next_sig = _SIGNATURE.search(text, emphasis_abs_start + 1)
                    next_fin = _FINANCIAL_STATEMENT_HEADINGS.search(
                        text, emphasis_abs_start + 1
                    )
                    candidates = [c for c in [
                        (next_sig.start() + 600) if next_sig else None,
                        next_fin.start() if next_fin else None,
                        emphasis_region_end,
                    ] if c is not None]
                    report_end = min(candidates)
                    logger.debug(
                        "Extended report end to %d to include emphasis-of-matter "
                        "section at %d in filing %s",
                        report_end, emphasis_abs_start, filing_id,
                    )
                else:
                    # No emphasis section found — 600 chars captures firm + date line
                    report_end = min(sig_match.end() + 600, len(text))

                if is_confirmed_real:
                    extraction_method = "heading_match_v2_fallback"
                    confidence = "medium"
                else:
                    extraction_method = "heading_match_v2_ambiguous"
                    confidence = "low"
            else:
                # Last resort: cap at 5,000 chars from heading
                report_end = min(report_start + 5000, len(text))
                extraction_method = "heading_match_v2_ambiguous"
                confidence = "low"

        report_text = text[report_start:report_end].strip()

        if len(report_text) < _MIN_REPORT_CHARS:
            # The extracted section is suspiciously short; skip this hit
            continue

        # ── 4b. Truncate over-extracted reports ──────────────────────────
        if len(report_text) > _MAX_REPORT_CHARS:
            report_text = _truncate_at_signature(report_text, filing_id)

        # ── 4. Identify audit firm ───────────────────────────────────────
        firm_match = _AUDIT_FIRMS.search(report_text)
        audit_firm = firm_match.group(0).strip() if firm_match else None

        logger.info(
            "Extracted auditor report from %s: firm=%s method=%s confidence=%s chars=%d",
            filing_id,
            audit_firm,
            extraction_method,
            confidence,
            len(report_text),
        )

        return AuditorReportExtraction(
            report_text=report_text,
            audit_firm=audit_firm,
            extraction_method=extraction_method,
            char_offset_start=report_start,
            char_offset_end=report_end,
            confidence=confidence,
        )

    logger.warning("No auditor report section found in filing %s", filing_id)
    return None


def _truncate_at_signature(report_text: str, filing_id: str) -> str:
    """Truncate an over-extracted auditor report at the last valid signature boundary.

    Searches for the last ``/s/ ...`` or city+date line within the first
    ``_MAX_REPORT_CHARS`` characters.  If none is found the first
    ``_MAX_REPORT_CHARS`` characters are returned with a warning.
    """
    search_region = report_text[:_MAX_REPORT_CHARS]

    # Find the *last* signature match in the first _MAX_REPORT_CHARS chars,
    # then extend 600 chars to capture firm name and date.
    best_end = 0
    for m in _SIGNATURE.finditer(search_region):
        best_end = min(m.end() + 600, len(report_text))

    # Also check for a date line (city, state  Month D, YYYY) in that region
    for m in _DATE_LINE.finditer(search_region):
        candidate = min(m.end() + 200, len(report_text))
        if candidate > best_end:
            best_end = candidate

    if best_end > _MIN_REPORT_CHARS:
        logger.info(
            "Truncated over-extracted report in %s from %d to %d chars "
            "(boundary found at %d)",
            filing_id,
            len(report_text),
            best_end,
            best_end,
        )
        return report_text[:best_end].strip()

    logger.warning(
        "Over-extracted report in %s (%d chars) with no signature boundary; "
        "keeping first %d chars",
        filing_id,
        len(report_text),
        _MAX_REPORT_CHARS,
    )
    return report_text[:_MAX_REPORT_CHARS].strip()


def _html_to_clean_text(soup: BeautifulSoup) -> str:
    """Convert BeautifulSoup tree to whitespace-normalised plain text.

    Uses BeautifulSoup's built-in get_text with a newline separator so that
    block-level elements produce natural paragraph breaks.  Runs of blank
    lines are collapsed and intra-line whitespace is compressed.
    """
    # Strip <script> and <style> nodes that would pollute the text
    for tag in soup(["script", "style"]):
        tag.decompose()

    raw = soup.get_text(separator="\n")
    # Compress horizontal whitespace (but not \xa0 which is handled below)
    raw = re.sub(r"[ \t]+", " ", raw)
    # Rejoin all-caps words split across lines by filing-agent HTML layout.
    # Donnelley Financial Solutions (filer 0000950170) wraps long headings
    # mid-word, producing e.g. "REGIST\nERED".  This prevents heading patterns
    # from matching.  We detect runs of 2+ uppercase letters on adjacent lines
    # and merge them.
    raw = re.sub(r"([A-Z]{2,})\n([A-Z]{2,})", r"\1\2", raw)
    # Collapse runs of blank lines to a single blank line
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw
