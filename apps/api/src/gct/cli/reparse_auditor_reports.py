"""Re-parse auditor reports from already-downloaded filing HTML.

This command re-runs the auditor-report extractor against every 10-K filing
that has a raw HTML file on disk, without making any new SEC EDGAR requests.
It is idempotent: running it multiple times produces the same result.

Useful after improving filing_parser.py (e.g. the TOC false-positive fix in
Prompt 2.1) to re-extract all stored filings without a full re-download.

Usage:
    python -m gct.cli.reparse_auditor_reports
    python -m gct.cli.reparse_auditor_reports --verbose
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from gct.database import SessionLocal
from gct.ingestion.filing_parser import AuditorReportExtraction, extract_auditor_report
from gct.ingestion.persistence import upsert_auditor_report
from gct.models import AuditorReport, Filing

logging.basicConfig(level=logging.WARNING, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False)
console = Console()

# Canonical ordering for comparing extraction confidence levels.
_CONFIDENCE_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}

# Infer confidence from the extraction_method stored in the DB (since we don't
# store confidence as its own column).
_METHOD_TO_CONFIDENCE: dict[str, str] = {
    "heading_match_v1": "high",
    "heading_match_v2_fallback": "medium",
    "heading_match_v2_ambiguous": "low",
}


def _method_confidence(method: str) -> str:
    return _METHOD_TO_CONFIDENCE.get(method, "low")


@dataclass
class _Stats:
    total_filings: int = 0
    skipped_no_file: int = 0
    skipped_no_report: int = 0
    added: int = 0
    unchanged: int = 0
    longer: int = 0
    shorter: int = 0
    confidence_upgraded: int = 0
    method_changed: int = 0

    # Details for the per-filing table
    rows: list[dict] = field(default_factory=list)


@app.command()
def reparse_auditor_reports(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-filing detail"),
) -> None:
    """Re-extract auditor reports from on-disk HTML; update DB rows in place."""
    if verbose:
        logging.getLogger("gct").setLevel(logging.INFO)

    console.print("\n[bold]Going Concern Tracker — Re-parse Auditor Reports[/bold]\n")

    db = SessionLocal()
    stats = _Stats()

    try:
        filings = (
            db.execute(
                select(Filing)
                .where(Filing.form_type == "10-K", Filing.raw_text_path.is_not(None))
                .order_by(Filing.filing_date.desc())
            )
            .scalars()
            .all()
        )

        stats.total_filings = len(filings)
        console.print(f"Found [cyan]{stats.total_filings}[/cyan] 10-K filing(s) with stored HTML.\n")

        for filing in filings:
            row: dict = {
                "accession": filing.accession_number,
                "date": str(filing.filing_date),
                "result": "",
                "old_chars": 0,
                "new_chars": 0,
                "old_method": "",
                "new_method": "",
            }

            path = Path(filing.raw_text_path)  # type: ignore[arg-type]
            if not path.exists():
                stats.skipped_no_file += 1
                row["result"] = "SKIP (no file)"
                stats.rows.append(row)
                continue

            # Re-run the extractor against the stored HTML
            html = path.read_text(encoding="utf-8")
            new_extraction = extract_auditor_report(
                html, "10-K", filing_id=filing.accession_number
            )

            if new_extraction is None:
                stats.skipped_no_report += 1
                row["result"] = "SKIP (no report found)"
                stats.rows.append(row)
                continue

            # Fetch the existing DB row (may be None for new filings)
            existing = db.execute(
                select(AuditorReport).where(AuditorReport.filing_id == filing.id)
            ).scalar_one_or_none()

            if existing is None:
                upsert_auditor_report(db, filing.id, new_extraction)
                db.commit()
                stats.added += 1
                row["result"] = "ADDED"
                row["new_chars"] = len(new_extraction.report_text)
                row["new_method"] = new_extraction.extraction_method
            else:
                old_len = len(existing.report_text)
                new_len = len(new_extraction.report_text)
                old_method = existing.extraction_method
                new_method = new_extraction.extraction_method

                row["old_chars"] = old_len
                row["new_chars"] = new_len
                row["old_method"] = old_method
                row["new_method"] = new_method

                old_conf = _CONFIDENCE_RANK.get(_method_confidence(old_method), 0)
                new_conf = _CONFIDENCE_RANK.get(new_extraction.confidence, 0)

                if new_conf > old_conf:
                    stats.confidence_upgraded += 1
                if new_method != old_method:
                    stats.method_changed += 1

                if new_len > old_len:
                    stats.longer += 1
                    row["result"] = "LONGER"
                elif new_len < old_len:
                    stats.shorter += 1
                    row["result"] = "SHORTER"
                else:
                    stats.unchanged += 1
                    row["result"] = "UNCHANGED"

                upsert_auditor_report(db, filing.id, new_extraction)
                db.commit()

            stats.rows.append(row)

    finally:
        db.close()

    _print_summary(stats, verbose)


def _print_summary(stats: _Stats, verbose: bool) -> None:
    if verbose and stats.rows:
        detail = Table(title="Per-filing detail", show_lines=False)
        detail.add_column("Accession", style="dim")
        detail.add_column("Date")
        detail.add_column("Result")
        detail.add_column("Old chars", justify="right")
        detail.add_column("New chars", justify="right")
        detail.add_column("Old method", style="dim")
        detail.add_column("New method")

        for r in stats.rows:
            result_style = {
                "ADDED": "[green]ADDED[/green]",
                "LONGER": "[cyan]LONGER[/cyan]",
                "SHORTER": "[yellow]SHORTER[/yellow]",
                "UNCHANGED": "UNCHANGED",
            }.get(r["result"], f"[dim]{r['result']}[/dim]")

            detail.add_row(
                r["accession"],
                r["date"],
                result_style,
                str(r["old_chars"]) if r["old_chars"] else "—",
                str(r["new_chars"]) if r["new_chars"] else "—",
                r["old_method"] or "—",
                r["new_method"] or "—",
            )

        console.print(detail)
        console.print()

    summary = Table(title="Re-parse Summary", show_lines=False)
    summary.add_column("Metric")
    summary.add_column("Count", justify="right")

    summary.add_row("Total 10-K filings with HTML", str(stats.total_filings))
    summary.add_row("Skipped (file missing from disk)", str(stats.skipped_no_file))
    summary.add_row("Skipped (parser returned None)", str(stats.skipped_no_report))
    summary.add_row("New report added (was None)", str(stats.added))
    summary.add_row("Report got longer", str(stats.longer))
    summary.add_row("Report got shorter", str(stats.shorter))
    summary.add_row("Report unchanged", str(stats.unchanged))
    summary.add_row("Confidence upgraded", str(stats.confidence_upgraded))
    summary.add_row("Extraction method changed", str(stats.method_changed))

    console.print(summary)


if __name__ == "__main__":
    app()
