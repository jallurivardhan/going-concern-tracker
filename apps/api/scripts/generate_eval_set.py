"""Generate the initial golden eval set from the current database state.

One-off script that:
  1. Reads all 38 classified filings from the database.
  2. For each, creates a golden-set case record whose expected_severity matches
     the current classification (which has been manually verified correct).
  3. Writes apps/api/eval/golden_set.json.

The output is hand-editable — the labeler_justification fields in particular
should be reviewed and refined before the eval set is considered authoritative.

Usage:
    cd apps/api
    python scripts/generate_eval_set.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from sqlalchemy import text

# Ensure src/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from gct.database import SessionLocal

OUT_PATH = Path(__file__).parents[1] / "eval" / "golden_set.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Company → metadata used in justifications and case_id slugs ──────────────

COMPANY_META: dict[str, dict] = {
    "0000320193": {
        "slug": "aapl",
        "short_name": "Apple Inc.",
        "auditor_override": "Ernst & Young LLP",
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=10-K",
    },
    "0000789019": {
        "slug": "msft",
        "short_name": "Microsoft Corp.",
        "auditor_override": "Deloitte & Touche LLP",
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000789019&type=10-K",
    },
    "0001639825": {
        "slug": "pton",
        "short_name": "Peloton Interactive",
        "auditor_override": None,
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001639825&type=10-K",
    },
    "0001655210": {
        "slug": "bynd",
        "short_name": "Beyond Meat Inc.",
        "auditor_override": None,
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001655210&type=10-K",
    },
    "0001130713": {
        "slug": "byon",
        "short_name": "Beyond, Inc. (BYON)",
        "auditor_override": None,
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001130713&type=10-K",
    },
    "0000886158": {
        "slug": "bbby_original",
        "short_name": "Bed Bath & Beyond Inc.",
        "auditor_override": None,
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000886158&type=10-K",
    },
    "0001813756": {
        "slug": "wework",
        "short_name": "WeWork Inc.",
        "auditor_override": None,
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001813756&type=10-K",
    },
    "0001008654": {
        "slug": "tupperware",
        "short_name": "Tupperware Brands Corp.",
        "auditor_override": None,
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001008654&type=10-K",
    },
}

# Special-case justifications (override the template for specific accessions).
SPECIAL_JUSTIFICATIONS: dict[str, str] = {
    # Tupperware FY2022 critical
    "0001008654-23-000079": (
        "PricewaterhouseCoopers LLP issued a formal going-concern opinion on Tupperware Brands "
        "Corporation's FY2022 financial statements (fiscal year ended December 31, 2022). "
        "The auditor's report contains a 'Substantial Doubt about the Company's Ability to "
        "Continue as a Going Concern' section heading and explicitly cites liquidity challenges "
        "and uncertainty about compliance with debt covenants as conditions raising substantial "
        "doubt. This constitutes a formal PCAOB AS 2415 going-concern opinion modifier."
    ),
    # BBBY original FY2022 critical
    "0000886158-23-000059": (
        "KPMG LLP issued a formal going-concern opinion on Bed Bath & Beyond Inc.'s FY2022 "
        "financial statements (fiscal year ended February 25, 2023, filed June 2023 — late "
        "due to liquidity crisis). The auditor's report includes a 'Going Concern' emphasis "
        "section stating the Company has 'suffered recurring losses from operations and negative "
        "cash flows from operations that raise substantial doubt about its ability to continue "
        "as a going concern.' The Company filed for Chapter 11 bankruptcy in April 2023. "
        "Note: the SEC entity is now 'DK-Butterfly-1' (the successor shell), but the audit "
        "report text references Bed Bath & Beyond Inc. by name."
    ),
    # WeWork FY2022 — the canonical 'false negative at auditor-report level' case
    "0001813756-23-000016": (
        "Ernst & Young LLP issued a CLEAN (unqualified) opinion on WeWork Inc.'s FY2022 "
        "financial statements (fiscal year ended December 31, 2022, filed March 29, 2023). "
        "Going-concern language DOES appear in the filing, but exclusively in management's "
        "disclosures: the MD&A 'Critical Accounting Estimates' section (around page 102) and "
        "Note 19 to the financial statements. EY's audit opinion itself contains no "
        "'Emphasis of Matter' or going-concern modification. Per this system's defined scope "
        "(auditor's-report classification only), the correct expected_severity is 'none'. "
        "A Phase 2 expansion covering MD&A and note-level disclosures would classify this "
        "as 'watch' or 'elevated'. This is the canonical documented edge case."
    ),
    # WeWork FY2021
    "0001813756-22-000003": (
        "Ernst & Young LLP issued a clean opinion on WeWork Inc.'s FY2021 financial statements. "
        "No going-concern modification in the auditor's report. WeWork's going-concern risk was "
        "disclosed in management notes but not formally flagged by the auditor in FY2021."
    ),
    # WeWork FY2020 (filed via a different filer)
    "0001193125-21-092791": (
        "WeWork Inc. FY2020 10-K (filed by form registration entity 0001193125). "
        "Auditor report section was not successfully extracted by the parser (confidence=low). "
        "Based on public record, no formal going-concern opinion was issued for FY2020. "
        "Expected severity: none."
    ),
}


def _infer_fy(filing_date: date, cik: str) -> str:
    """Infer approximate fiscal year label from filing date."""
    # Companies with non-December fiscal years that file in the same calendar year
    # Apple (FY ends Sep): filed Oct-Nov → FY = filing_year
    # Microsoft (FY ends Jun): filed Jul → FY = filing_year
    # Peloton (FY ends Jun): filed Aug → FY = filing_year
    if cik in ("0000320193", "0000789019", "0001639825"):
        return f"fy{filing_date.year}"
    # All others: typical December FY, filed Jan-Jun of following year
    # (or very late, like Tupperware filing Oct 2023 for FY2022)
    if filing_date.month <= 9:
        return f"fy{filing_date.year - 1}"
    # Oct-Dec filings with Dec-FY: very late filer → year-1
    return f"fy{filing_date.year - 1}"


def _clean_audit_firm(firm: str | None) -> str:
    if not firm:
        return "the auditor"
    # Strip Unicode noise (KPMG\u2019LLP → KPMG LLP)
    return re.sub(r"[\u2018\u2019\u201c\u201d\u00a0\ufffd]", " ", firm).strip()


def _make_justification(
    cik: str,
    accession: str,
    filing_date: date,
    severity: str,
    company_name: str,
    audit_firm: str | None,
    quoted_language: str | None,
) -> str:
    """Generate a labeler justification for a case."""
    if accession in SPECIAL_JUSTIFICATIONS:
        return SPECIAL_JUSTIFICATIONS[accession]

    meta = COMPANY_META.get(cik, {})
    short_name = meta.get("short_name") or company_name
    firm = _clean_audit_firm(meta.get("auditor_override") or audit_firm)

    if severity == "none":
        return (
            f"{firm} issued a clean, unqualified audit opinion on {short_name}'s "
            f"{filing_date.year} annual report. No going-concern modification, "
            f"emphasis paragraph, or substantial-doubt language appears in the auditor's report."
        )

    # Critical/elevated: reference the stored quote
    quote_snippet = (quoted_language or "")[:200].strip()
    return (
        f"{firm} issued a going-concern opinion on {short_name}'s annual report "
        f"(filed {filing_date}). The auditor's report contains the following language: "
        f'"{quote_snippet}..." '
        f"This constitutes a formal PCAOB AS 2415 going-concern opinion modifier."
    )


def _make_case_id(cik: str, filing_date: date) -> str:
    meta = COMPANY_META.get(cik, {})
    slug = meta.get("slug") or "company"
    fy = _infer_fy(filing_date, cik)
    return f"{slug}_{fy}_{filing_date.isoformat()}"


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT c.name, c.ticker, c.cik, f.filing_date, f.accession_number,"
            "       f.form_type, gcf.severity, gcf.flag_type,"
            "       gcf.quoted_language, ar.audit_firm"
            " FROM going_concern_flags gcf"
            " JOIN filings f ON f.id = gcf.filing_id"
            " JOIN companies c ON c.id = gcf.company_id"
            " LEFT JOIN auditor_reports ar ON ar.filing_id = f.id"
            " ORDER BY c.cik, f.filing_date DESC"
        )).fetchall()

        print(f"Found {len(rows)} classified filings.")

        cases = []
        severity_counts: dict[str, int] = {}
        for r in rows:
            filing_date = r.filing_date
            cik = r.cik
            accession = r.accession_number
            severity = r.severity
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

            meta = COMPANY_META.get(cik, {})
            ticker_or_name = r.ticker or meta.get("short_name") or r.name

            expected_phrase = None
            if severity in ("critical", "elevated") and r.quoted_language:
                # Extract a short but distinctive phrase for verification
                q = r.quoted_language.lower()
                if "substantial doubt" in q:
                    expected_phrase = "substantial doubt"
                elif "going concern" in q:
                    expected_phrase = "going concern"

            case = {
                "case_id": _make_case_id(cik, filing_date),
                "company_ticker_or_name": ticker_or_name,
                "company_cik": cik,
                "filing_accession": accession,
                "filing_date": filing_date.isoformat(),
                "filing_form_type": r.form_type,
                "expected_severity": severity,
                "expected_flag_type": r.flag_type,
                "expected_has_going_concern": severity != "none",
                "expected_quoted_phrase_contains": expected_phrase,
                "labeler_justification": _make_justification(
                    cik=cik,
                    accession=accession,
                    filing_date=filing_date,
                    severity=severity,
                    company_name=r.name,
                    audit_firm=r.audit_firm,
                    quoted_language=r.quoted_language,
                ),
                "source_evidence_url": meta.get("source_url", ""),
            }
            cases.append(case)

        golden_set = {
            "version": "v1.0",
            "created_at": date.today().isoformat(),
            "labeler": "vardhan_jalluri",
            "methodology_version": "v1.0",
            "cases": cases,
        }

        OUT_PATH.write_text(
            json.dumps(golden_set, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Written: {OUT_PATH}  ({len(cases)} cases)")
        for sev, count in sorted(severity_counts.items()):
            print(f"  expected_severity={sev}: {count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
