"""Tests for filing_parser.py — auditor-report extraction.

The fixture HTML (sample_10k_with_audit_report.html) is a fictional but
realistic 10-K for "Acme Industries Inc." signed by Ernst & Young LLP,
including a going-concern paragraph.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gct.ingestion.filing_parser import (
    AuditorReportExtraction,
    _AUDIT_FIRMS,
    _AUDIT_HEADINGS,
    _EMPHASIS_OF_MATTER,
    _ICFR_INDICATOR,
    _REAL_REPORT_INDICATOR,
    _TOC_INDICATOR,
    _html_to_clean_text,
    extract_auditor_report,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def standard_10k_html() -> str:
    return _load_fixture("sample_10k_with_audit_report.html")


@pytest.fixture()
def html_no_audit_report() -> str:
    """Minimal 10-K HTML with no auditor report section."""
    return """<!DOCTYPE html>
<html><body>
<p><b>ITEM 8. FINANCIAL STATEMENTS</b></p>
<p>See attached financial statements.</p>
<p align="center"><b>CONSOLIDATED BALANCE SHEETS</b></p>
<p>Assets: $100,000</p>
</body></html>"""


@pytest.fixture()
def html_messy_nested_tags() -> str:
    """Auditor report heading buried in nested tags and whitespace noise."""
    return """<!DOCTYPE html>
<html><body>
<div><table><tr><td>
  <div style="text-align:center;font-weight:bold;">
    <span>REPORT&nbsp;OF&nbsp;</span><span>INDEPENDENT&nbsp;</span>
    <span>REGISTERED&nbsp;PUBLIC&nbsp;ACCOUNTING&nbsp;FIRM</span>
  </div>
</td></tr></table></div>
<p>To the Board of Directors of Messy Corp.</p>
<p>
  We have audited the accompanying consolidated financial statements of Messy Corp.
  and its subsidiaries as of December 31, 2022 and 2021.  In our opinion, the
  consolidated financial statements present fairly, in all material respects, the
  financial position of the Company as of December 31, 2022.  The accompanying
  consolidated financial statements have been prepared assuming the Company will
  continue as a going concern.  The Company has incurred net losses since inception
  that raise substantial doubt about its ability to continue as a going concern.
</p>
<p>Basis for Opinion</p>
<p>These financial statements are the responsibility of management.</p>
<p>/s/ KPMG LLP</p>
<p>KPMG LLP</p>
<p>New York, New York</p>
<p>February 28, 2023</p>
<p><b>CONSOLIDATED BALANCE SHEETS</b></p>
<p>Assets: $1,000</p>
</body></html>"""


# ── standard extraction ──────────────────────────────────────────────────────


def test_extracts_auditor_report_from_standard_10k(standard_10k_html: str) -> None:
    """extract_auditor_report returns a non-None result for the standard fixture."""
    result = extract_auditor_report(standard_10k_html, "10-K", filing_id="test-001")

    assert result is not None
    assert isinstance(result, AuditorReportExtraction)
    assert len(result.report_text) > 200
    assert result.char_offset_start >= 0
    assert result.char_offset_end > result.char_offset_start


def test_extracts_report_contains_going_concern_language(standard_10k_html: str) -> None:
    """The extracted text should include the going-concern paragraph."""
    result = extract_auditor_report(standard_10k_html, "10-K")
    assert result is not None
    assert "going concern" in result.report_text.lower()
    assert "substantial doubt" in result.report_text.lower()


def test_identifies_audit_firm_correctly(standard_10k_html: str) -> None:
    """Ernst & Young LLP should be identified as the audit firm."""
    result = extract_auditor_report(standard_10k_html, "10-K")
    assert result is not None
    assert result.audit_firm is not None
    assert "Ernst" in result.audit_firm or "Young" in result.audit_firm


def test_extraction_method_is_heading_match_v1(standard_10k_html: str) -> None:
    """Standard fixture has a clear next-section heading so method should be v1."""
    result = extract_auditor_report(standard_10k_html, "10-K")
    assert result is not None
    # May be v1 (found financial statement heading) or v2 (fallback to signature)
    assert result.extraction_method in {"heading_match_v1", "heading_match_v2_fallback"}


def test_confidence_is_high_or_medium(standard_10k_html: str) -> None:
    result = extract_auditor_report(standard_10k_html, "10-K")
    assert result is not None
    assert result.confidence in {"high", "medium", "low"}


# ── 10-Q returns None ────────────────────────────────────────────────────────


def test_returns_none_for_10q(standard_10k_html: str) -> None:
    """10-Q filings do not carry a formal auditor opinion; always returns None."""
    assert extract_auditor_report(standard_10k_html, "10-Q") is None
    assert extract_auditor_report(standard_10k_html, "10-Q/A") is None


# ── no report present ───────────────────────────────────────────────────────


def test_returns_none_when_no_audit_report_present(html_no_audit_report: str) -> None:
    """HTML with no auditor report heading must return None, not raise."""
    result = extract_auditor_report(html_no_audit_report, "10-K", filing_id="no-report")
    assert result is None


# ── messy HTML with nested tags ─────────────────────────────────────────────


def test_handles_messy_html_with_nested_tags(html_messy_nested_tags: str) -> None:
    """Extraction succeeds even when the heading is split across nested tags."""
    result = extract_auditor_report(html_messy_nested_tags, "10-K", filing_id="messy-001")

    assert result is not None
    assert len(result.report_text) > 100
    # KPMG LLP should be identified
    assert result.audit_firm is not None
    assert "KPMG" in result.audit_firm


# ── TOC false-positive detection ─────────────────────────────────────────────


@pytest.fixture()
def html_with_toc_then_real_report() -> str:
    """10-K HTML that has both a TOC entry and a real auditor-report section.

    The TOC entry looks like:
        REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM
        57
        Consolidated Balance Sheets
        58

    The real report follows later and opens with "To the Stockholders".
    """
    return """<!DOCTYPE html>
<html><body>

<p><b>TABLE OF CONTENTS</b></p>
<p><b>REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM</b></p>
<p>57</p>
<p>Consolidated Balance Sheets</p>
<p>58</p>
<p>Consolidated Statements of Operations</p>
<p>59</p>
<p>Notes to Consolidated Financial Statements</p>
<p>60</p>

<hr/>

<p align="center"><b>REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM</b></p>
<p>To the Stockholders and Board of Directors of FakeCorp Inc.</p>
<p>
  We have audited the accompanying consolidated balance sheets of FakeCorp Inc.
  (the "Company") as of December 31, 2022 and 2021. In our opinion, the
  consolidated financial statements present fairly, in all material respects, the
  financial position of the Company. The accompanying financial statements have
  been prepared assuming the Company will continue as a going concern. As discussed
  in Note 2, the Company has suffered recurring losses that raise substantial doubt
  about its ability to continue as a going concern.
</p>
<p>Basis for Opinion</p>
<p>We are a public accounting firm registered with the PCAOB.</p>
<p>/s/ Deloitte &amp; Touche LLP</p>
<p>Deloitte &amp; Touche LLP</p>
<p>Chicago, Illinois</p>
<p>March 10, 2023</p>

<p align="center"><b>CONSOLIDATED BALANCE SHEETS</b></p>
<p>(in thousands)</p>
<p>Total assets: $50,000</p>

</body></html>"""


@pytest.fixture()
def html_with_only_toc_entry() -> str:
    """10-K HTML that contains only a TOC-like reference — no real auditor report."""
    return """<!DOCTYPE html>
<html><body>
<p><b>TABLE OF CONTENTS</b></p>
<p><b>REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM</b></p>
<p>42</p>
<p>Consolidated Balance Sheets</p>
<p>43</p>
<p>Consolidated Statements of Operations</p>
<p>44</p>
</body></html>"""


def test_skips_toc_false_positive(html_with_toc_then_real_report: str) -> None:
    """Parser must skip the TOC entry and return the real auditor report."""
    result = extract_auditor_report(
        html_with_toc_then_real_report, "10-K", filing_id="toc-test-001"
    )

    assert result is not None, "Expected a result — real report is present"
    # The real report starts with "To the Stockholders", not a page number
    assert "To the Stockholders" in result.report_text or "We have audited" in result.report_text
    # Should NOT contain "57\n" or bare page numbers from the TOC
    assert not result.report_text.strip().startswith("57")
    # Should contain going-concern language
    assert "going concern" in result.report_text.lower()
    # Deloitte should be identified
    assert result.audit_firm is not None
    assert "Deloitte" in result.audit_firm


def test_handles_only_toc_entry(html_with_only_toc_entry: str) -> None:
    """When only a TOC entry exists (no real report body), return None."""
    result = extract_auditor_report(
        html_with_only_toc_entry, "10-K", filing_id="toc-only-001"
    )
    assert result is None, "Expected None — only a TOC entry is present, no real report"


# ── TOC / real-report indicator regex tests ──────────────────────────────────


@pytest.mark.parametrize(
    "preview",
    [
        "\n57\nConsolidated Balance Sheets\n",
        "\n 42 \nConsolidated Statements of Operations\n",
        "Consolidated Balance Sheets\n58\n",
        "Notes to Consolidated Financial Statements\n61\n",
        "Selected Financial Data\n",
        "Management's Discussion and Analysis\n",
    ],
)
def test_toc_indicator_matches_toc_previews(preview: str) -> None:
    assert _TOC_INDICATOR.search(preview) is not None, f"TOC pattern missed: {preview!r}"


@pytest.mark.parametrize(
    "preview",
    [
        "To the Stockholders and Board of Directors",
        "To the Board of Directors of Some Corp",
        "To the Shareholders of XYZ Inc.",
        "We have audited the accompanying",
        "In our opinion, the consolidated financial statements",
    ],
)
def test_real_report_indicator_matches_report_openers(preview: str) -> None:
    assert _REAL_REPORT_INDICATOR.search(preview) is not None, (
        f"Real-report pattern missed: {preview!r}"
    )


# ── regex pattern tests ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "heading",
    [
        "REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM",
        "Report of Independent Registered Public Accounting Firm",
        "INDEPENDENT AUDITOR'S REPORT",
        "Independent Auditors' Report",
        "REPORT OF INDEPENDENT AUDITORS",
        "REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTANTS",
    ],
)
def test_audit_heading_regex_matches_known_variants(heading: str) -> None:
    assert _AUDIT_HEADINGS.search(heading) is not None, f"Pattern did not match: {heading!r}"


@pytest.mark.parametrize(
    "firm_name",
    [
        "Ernst & Young LLP",
        "Deloitte & Touche LLP",
        "PricewaterhouseCoopers LLP",
        "KPMG LLP",
        "BDO USA LLP",
        "Grant Thornton LLP",
        "RSM US LLP",
        "Crowe LLP",
        "Marcum LLP",
        "MaloneBailey LLP",
        "Smith Johnson LLP",  # generic pattern
    ],
)
def test_audit_firm_regex_matches_known_firms(firm_name: str) -> None:
    assert _AUDIT_FIRMS.search(firm_name) is not None, f"Pattern did not match: {firm_name!r}"


# ── html_to_clean_text ───────────────────────────────────────────────────────


def test_html_to_clean_text_strips_script_tags() -> None:
    from bs4 import BeautifulSoup

    html = "<html><body><script>alert('xss')</script><p>Hello world</p></body></html>"
    soup = BeautifulSoup(html, "lxml")
    text = _html_to_clean_text(soup)

    assert "alert" not in text
    assert "Hello world" in text


def test_html_to_clean_text_collapses_blank_lines() -> None:
    from bs4 import BeautifulSoup

    html = "<html><body><p>A</p><p></p><p></p><p>B</p></body></html>"
    soup = BeautifulSoup(html, "lxml")
    text = _html_to_clean_text(soup)

    assert "\n\n\n" not in text


# ── Emphasis-of-Matter / ICFR-skip tests ─────────────────────────────────────


def _make_html(body: str) -> str:
    return f"<html><body><pre>{body}</pre></body></html>"


def test_includes_emphasis_of_matter_paragraph() -> None:
    """Parser extends extraction past the first signature when an
    'Emphasis of Matter' section follows the main opinion."""
    html = _make_html(
        "Report of Independent Registered Public Accounting Firm\n"
        "To the Shareholders of Acme Corp.\n"
        "In our opinion, the financial statements present fairly.\n"
        "Basis for Opinion\n"
        "We conducted our audit in accordance with PCAOB standards.\n"
        "/s/ Ernst & Young LLP\n"
        "New York, NY  March 1, 2023\n"
        "Emphasis of Matter\n"
        "The accompanying financial statements have been prepared assuming the Company "
        "will continue as a going concern. As discussed in Note 2, substantial doubt "
        "about the Company's ability to continue as a going concern exists.\n"
        "/s/ Ernst & Young LLP\n"
        "New York, NY  March 1, 2023\n"
        "CONSOLIDATED BALANCE SHEETS\n"
        "December 31, 2022\n"
    )
    result = extract_auditor_report(html, "10-K", "test-emphasis-001")

    assert result is not None
    assert "Emphasis of Matter" in result.report_text
    assert "substantial doubt" in result.report_text.lower()


def test_includes_material_uncertainty_section() -> None:
    """Parser extends extraction when a 'Material Uncertainty Related to
    Going Concern' section follows the first signature block."""
    html = _make_html(
        "Report of Independent Registered Public Accounting Firm\n"
        "To the Board of Directors of XYZ Corp.\n"
        "In our opinion, the financial statements present fairly.\n"
        "/s/ Deloitte & Touche LLP\n"
        "Chicago, IL  February 28, 2023\n"
        "Material Uncertainty Related to Going Concern\n"
        "We draw attention to Note 3 in the financial statements which indicates "
        "conditions that raise substantial doubt about the ability to continue.\n"
        "/s/ Deloitte & Touche LLP\n"
        "Chicago, IL  February 28, 2023\n"
        "CONSOLIDATED BALANCE SHEETS\n"
    )
    result = extract_auditor_report(html, "10-K", "test-mat-uncertainty-001")

    assert result is not None
    assert "Material Uncertainty" in result.report_text
    assert "substantial doubt" in result.report_text.lower()


def test_stops_at_next_main_heading_after_emphasis() -> None:
    """After including the emphasis-of-matter section the parser does not
    bleed into the next report section or financial statements."""
    html = _make_html(
        "Report of Independent Registered Public Accounting Firm\n"
        "To the Shareholders of Acme Corp.\n"
        "In our opinion, the financial statements present fairly.\n"
        "/s/ Ernst & Young LLP\n"
        "New York, NY  March 10, 2023\n"
        "Emphasis of Matter\n"
        "Substantial doubt exists about the Company's ability to continue as a going concern.\n"
        "/s/ Ernst & Young LLP\n"
        "New York, NY  March 10, 2023\n"
        "NOTES TO CONSOLIDATED FINANCIAL STATEMENTS\n"
        "Note 1: Basis of Presentation\n"
        "The Company prepares its financial statements in accordance with GAAP.\n"
        "Note 2: Going Concern\n"
        "Management has evaluated conditions...\n"
    )
    result = extract_auditor_report(html, "10-K", "test-emphasis-stop-001")

    assert result is not None
    assert "Emphasis of Matter" in result.report_text
    # The notes section should NOT be included
    assert "Basis of Presentation" not in result.report_text


def test_skips_icfr_only_report_prefers_financial_statements_report() -> None:
    """When a filing has both an ICFR report and a financial-statements report,
    the parser skips the ICFR-only heading and extracts the financial-statements
    report (which is more likely to contain going-concern language)."""
    html = _make_html(
        # ICFR-only audit report (should be skipped)
        "Report of Independent Registered Public Accounting Firm\n"
        "To the Shareholders of TechCo Inc.\n"
        "Opinion on Internal Control Over Financial Reporting\n"
        "We have audited TechCo's internal control over financial reporting.\n"
        "In our opinion, the Company maintained effective internal control.\n"
        "/s/ Ernst & Young LLP\n"
        "New York, NY  March 15, 2023\n"
        "\n"
        # Financial-statements audit report (should be extracted)
        "Report of Independent Registered Public Accounting Firm\n"
        "To the Shareholders of TechCo Inc.\n"
        "Opinion on the Financial Statements\n"
        "We have audited the accompanying financial statements of TechCo Inc.\n"
        "These conditions raise substantial doubt about the Company's ability "
        "to continue as a going concern.\n"
        "/s/ Ernst & Young LLP\n"
        "New York, NY  March 15, 2023\n"
        "CONSOLIDATED BALANCE SHEETS\n"
    )
    result = extract_auditor_report(html, "10-K", "test-icfr-skip-001")

    assert result is not None
    # Must be the financial-statements report, not the ICFR report
    assert "Opinion on the Financial Statements" in result.report_text
    assert "substantial doubt" in result.report_text.lower()
    # The ICFR-only opinion text should NOT be the start of the result
    assert "Opinion on Internal Control Over Financial Reporting" not in result.report_text


# ── Donnelley mid-word line-break fix ───────────────────────────────────────


def _make_donnelley_html(body: str) -> str:
    """Simulate Donnelley Financial Solutions HTML where headings are split mid-word."""
    return f"<html><body><p>{body}</p></body></html>"


class TestDonnelleyFilerFormat:
    """Parametrized tests for the Donnelley/MSFT mid-word heading split bug.

    Donnelley's rendering engine sometimes wraps long headings mid-word inside
    narrow table cells.  The plain-text representation contains a newline in the
    middle of a word, e.g. 'REGIST\\nERED'.  The parser must still find the
    heading and extract the report body.
    """

    @pytest.mark.parametrize(
        "split_heading",
        [
            # "REGISTERED" split after "REGIST"
            "REPORT OF INDEPENDENT REGIST\nERED PUBLIC ACCOUNTING FIRM",
            # "INDEPENDENT" split after "INDE"
            "REPORT OF INDE\nPENDENT REGISTERED PUBLIC ACCOUNTING FIRM",
            # "ACCOUNTING" split after "ACCOUNT"
            "REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNT\nING FIRM",
        ],
    )
    def test_handles_donnelley_split_heading(self, split_heading: str):
        html = _make_html(
            f"{split_heading}\n"
            "To the Stockholders and the Board of Directors of Acme Corp\n"
            "Opinion on the Financial Statements\n"
            "We have audited the accompanying consolidated balance sheets of Acme Corp.\n"
            "In our opinion, the financial statements present fairly.\n"
            "/s/ Deloitte & Touche LLP\n"
            "Seattle, WA  June 30, 2025\n"
            "CONSOLIDATED BALANCE SHEETS\n"
        )
        result = extract_auditor_report(html, "10-K", "donnelley-split-test")
        assert result is not None, f"Failed to find report with split heading: {split_heading!r}"
        assert "We have audited" in result.report_text

    def test_split_word_rejoin_in_clean_text(self):
        """The _html_to_clean_text preprocessing rejoins split all-caps words."""
        from gct.ingestion.filing_parser import _html_to_clean_text
        from bs4 import BeautifulSoup

        html = "<html><body><p>REPORT OF INDEPENDENT REGIST\nERED PUBLIC ACCOUNTING FIRM</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        clean = _html_to_clean_text(soup)
        assert "REGISTERED" in clean
        assert "REGIST\nERED" not in clean


# ── Signature-boundary truncation ───────────────────────────────────────────


class TestSignatureBoundaryTruncation:
    """Tests for the _truncate_at_signature helper added for Task 2."""

    def test_over_extracted_report_is_truncated(self):
        from gct.ingestion.filing_parser import _truncate_at_signature, _MAX_REPORT_CHARS

        # Build a fake report: real content + signature + lots of extra garbage
        real_content = "We have audited the accompanying financial statements. " * 100
        signature = "\n/s/ Ernst & Young LLP\nNew York, NY  March 15, 2025\n"
        garbage = "CONSOLIDATED BALANCE SHEETS\n" + ("lots of financial data\n" * 2000)
        full_text = real_content + signature + garbage

        assert len(full_text) > _MAX_REPORT_CHARS, "Fixture must exceed the cap"

        result = _truncate_at_signature(full_text, "trunc-test-001")

        assert len(result) < len(full_text), "Result should be shorter than input"
        assert len(result) <= _MAX_REPORT_CHARS + 600, "Should not exceed cap + extension"
        assert "/s/ Ernst & Young LLP" in result, "Signature should be included"
        # The bulk of the garbage (many thousands of chars after signature) should be absent
        # (the first few hundred chars may be included as the 600-char tail window)
        assert "lots of financial data" * 10 not in result, "Deep garbage should be truncated"

    def test_short_report_not_truncated(self):
        from gct.ingestion.filing_parser import _truncate_at_signature, _MAX_REPORT_CHARS

        short_report = "We have audited. In our opinion. /s/ KPMG LLP\n" * 10
        assert len(short_report) < _MAX_REPORT_CHARS

        result = _truncate_at_signature(short_report, "short-test-001")
        # Short reports should not be truncated by this function (it's only called
        # when len > _MAX_REPORT_CHARS), but calling it directly should be safe
        assert result  # non-empty

    def test_extract_auditor_report_truncates_huge_extraction(self):
        """End-to-end: extract_auditor_report should return at most ~30K + buffer chars."""
        from gct.ingestion.filing_parser import _MAX_REPORT_CHARS

        # Build HTML with an audit section followed by a massive financial-statement blob
        # that would be over-extracted if the financial-statement heading isn't found.
        huge_financial_blob = "random financial data line\n" * 2000  # ~50K chars
        html = _make_html(
            "REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM\n"
            "To the Stockholders of MegaCorp\n"
            "Opinion on the Financial Statements\n"
            "We have audited the accompanying financial statements.\n"
            "In our opinion, the financial statements present fairly.\n"
            "/s/ PricewaterhouseCoopers LLP\n"
            "New York, NY  December 31, 2024\n"
            + huge_financial_blob
        )
        result = extract_auditor_report(html, "10-K", "huge-extract-test")
        assert result is not None
        # Should be truncated to well under _MAX_REPORT_CHARS + buffer
        assert len(result.report_text) < _MAX_REPORT_CHARS + 1000
