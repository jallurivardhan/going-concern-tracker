"""fix_offsets CLI — retroactively correct char_offset_start/end on existing flags.

Usage:
    python -m gct.cli.fix_offsets

Finds all GoingConcernFlag rows where:
  - severity != 'none'      (a real flag was stored)
  - char_offset_start == 0  AND char_offset_end == 0   (offsets were never computed)

For each such row, re-runs _find_quote_with_normalization against the current
AuditorReport.report_text and updates the row with correct offsets.

This is needed when previous classifications were written before the whitespace-
normalisation fix was added to the validator (offsets were defaulted to 0 when
str.find() returned -1 due to LLM whitespace collapsing).

The command is idempotent: rows that already have non-zero offsets are skipped.
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select, update

from gct.classifier.validator import _find_quote_with_normalization
from gct.database import SessionLocal
from gct.models import AuditorReport, Company, Filing, GoingConcernFlag

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def fix_offsets(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print what would be updated without writing to DB"
    ),
) -> None:
    """Re-compute char_offset_start/end for flags that have 0-0 offsets."""
    console.print("\n[bold]Going Concern Tracker — Fix Offsets[/bold]\n")

    db = SessionLocal()
    try:
        # Find flags with zero offsets where severity != 'none'
        rows = db.execute(
            select(GoingConcernFlag)
            .where(
                GoingConcernFlag.severity != "none",
                GoingConcernFlag.char_offset_start == 0,
                GoingConcernFlag.char_offset_end == 0,
            )
        ).scalars().all()

        if not rows:
            console.print("[green]No flags with 0-0 offsets found. Nothing to fix.[/green]")
            return

        console.print(f"Found {len(rows)} flag(s) with zero offsets to inspect.\n")

        fixed = 0
        skipped_no_quote = 0
        skipped_not_found = 0

        results: list[dict] = []

        for flag in rows:
            # Load related report
            filing = db.execute(
                select(Filing).where(Filing.id == flag.filing_id)
            ).scalar_one_or_none()
            company = db.execute(
                select(Company).where(Company.id == flag.company_id)
            ).scalar_one_or_none()
            report = db.execute(
                select(AuditorReport).where(AuditorReport.filing_id == flag.filing_id)
            ).scalar_one_or_none()

            label = f"{company.ticker or company.name} ({filing.accession_number if filing else '?'})"

            if not flag.quoted_language or not flag.quoted_language.strip():
                console.print(f"  [yellow]SKIP[/yellow] {label} — no quoted_language stored")
                skipped_no_quote += 1
                results.append({"label": label, "status": "skip:no_quote", "start": None, "end": None})
                continue

            if report is None:
                console.print(f"  [yellow]SKIP[/yellow] {label} — no AuditorReport row found")
                skipped_no_quote += 1
                results.append({"label": label, "status": "skip:no_report", "start": None, "end": None})
                continue

            offsets = _find_quote_with_normalization(flag.quoted_language, report.report_text)

            if offsets is None:
                console.print(f"  [red]NOT FOUND[/red] {label} — quote not found even after normalization")
                skipped_not_found += 1
                results.append({"label": label, "status": "not_found", "start": None, "end": None})
                continue

            start, end = offsets
            console.print(
                f"  [green]FIX[/green] {label}  "
                f"offsets: 0-0  ->  {start}-{end}"
            )

            if not dry_run:
                db.execute(
                    update(GoingConcernFlag)
                    .where(GoingConcernFlag.id == flag.id)
                    .values(char_offset_start=start, char_offset_end=end)
                )
                db.commit()

            fixed += 1
            results.append({"label": label, "status": "fixed", "start": start, "end": end})

        # Summary table
        table = Table(title="\nFix Offsets Summary", show_lines=False)
        table.add_column("Company / Accession", style="bold")
        table.add_column("Status")
        table.add_column("New start", justify="right")
        table.add_column("New end", justify="right")

        for r in results:
            status_fmt = {
                "fixed": "[green]fixed[/green]",
                "skip:no_quote": "[yellow]skip (no quote)[/yellow]",
                "skip:no_report": "[yellow]skip (no report)[/yellow]",
                "not_found": "[red]not found[/red]",
            }.get(r["status"], r["status"])
            table.add_row(
                r["label"],
                status_fmt,
                str(r["start"]) if r["start"] is not None else "-",
                str(r["end"]) if r["end"] is not None else "-",
            )

        console.print(table)
        console.print(
            f"\nResult: {fixed} fixed, "
            f"{skipped_no_quote} skipped, "
            f"{skipped_not_found} not found"
            + (" [DRY RUN — no writes committed]" if dry_run else "")
        )

        if skipped_not_found > 0:
            sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    app()
