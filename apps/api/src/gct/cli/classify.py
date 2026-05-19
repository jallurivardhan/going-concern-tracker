"""CLI: classify auditor reports using Claude.

Usage
-----
    # Classify all unclassified reports (default)
    python -m gct.cli.classify

    # Restrict to specific tickers
    python -m gct.cli.classify --tickers AAPL,MSFT

    # Re-classify even if a flag already exists
    python -m gct.cli.classify --force

    # Smoke test: only 1 report
    python -m gct.cli.classify --tickers AAPL --limit 1

    # Dry-run: print what would be written without touching the DB
    python -m gct.cli.classify --dry-run --limit 5
"""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from gct.classifier.classifier import classify_auditor_report
from gct.classifier.claude_client import ClaudeClassifier
from gct.classifier.schemas import ClassificationResult
from gct.config import settings
from gct.database import SessionLocal
from gct.models import AuditorReport, Company, Filing, GoingConcernFlag

logging.basicConfig(level=logging.WARNING, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False)
console = Console()

_SEVERITY_STYLE: dict[str, str] = {
    "critical": "[bold red]critical[/bold red]",
    "elevated": "[yellow]elevated[/yellow]",
    "watch": "[blue]watch[/blue]",
    "none": "[dim]none[/dim]",
}
_FLAG_TYPE_STYLE: dict[str, str] = {
    "new": "[bold green]new[/bold green]",
    "continuing": "[red]continuing[/red]",
    "resolved": "[cyan]resolved[/cyan]",
    "none": "[dim]none[/dim]",
}


@app.command()
def classify(
    tickers: str | None = typer.Option(
        None,
        "--tickers",
        help="Comma-separated list of tickers to classify (default: all)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-classify even if a GoingConcernFlag already exists",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Maximum number of reports to classify (useful for cost-controlled smoke tests)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run the full pipeline but skip writing to the database",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Classify auditor reports and write GoingConcernFlag rows."""
    if verbose:
        logging.getLogger("gct").setLevel(logging.INFO)

    console.print("\n[bold]Going Concern Tracker — Classify Auditor Reports[/bold]")
    if dry_run:
        console.print("[yellow]DRY RUN — no database writes[/yellow]")
    console.print()

    asyncio.run(
        _run(
            ticker_filter=_parse_tickers(tickers),
            force=force,
            limit=limit,
            dry_run=dry_run,
        )
    )


async def _run(
    ticker_filter: list[str] | None,
    force: bool,
    limit: int | None,
    dry_run: bool,
) -> None:
    client = ClaudeClassifier(
        anthropic_api_key=settings.anthropic_api_key,
        primary_model=settings.classifier_primary_model,
        fallback_model=settings.classifier_fallback_model,
        confidence_threshold=settings.classifier_confidence_threshold,
        max_retries=settings.classifier_max_retries,
        langfuse_public_key=settings.langfuse_public_key,
        langfuse_secret_key=settings.langfuse_secret_key,
        langfuse_host=settings.langfuse_host,
    )

    db = SessionLocal()
    results: list[tuple[str, str, ClassificationResult | None, str]] = []  # ticker, date, result, error

    try:
        reports = _query_reports(db, ticker_filter, force)
        if limit:
            reports = reports[:limit]

        total = len(reports)
        console.print(
            f"Found [cyan]{total}[/cyan] report(s) to classify"
            + (f" (limited to {limit})" if limit else "")
            + ".\n"
        )

        t_start = time.perf_counter()

        for idx, (report, filing, company) in enumerate(reports, 1):
            console.print(
                f"  [{idx}/{total}] {company.ticker}  {filing.filing_date}  "
                f"({filing.accession_number})"
            )

            try:
                if dry_run:
                    # In dry-run mode, call the classifier but do NOT commit
                    result = await classify_auditor_report(
                        session=db,
                        auditor_report_id=report.id,
                        client=client,
                        force=force,
                    )
                    db.rollback()
                else:
                    result = await classify_auditor_report(
                        session=db,
                        auditor_report_id=report.id,
                        client=client,
                        force=force,
                    )
                    db.commit()

                results.append((company.ticker, str(filing.filing_date), result, ""))

            except Exception as exc:
                db.rollback()
                logger.error("Failed to classify %s: %s", filing.accession_number, exc)
                results.append((company.ticker, str(filing.filing_date), None, str(exc)))

        total_elapsed = time.perf_counter() - t_start

    finally:
        db.close()

    _print_summary(results, client, total_elapsed, dry_run)


def _query_reports(
    db,
    ticker_filter: list[str] | None,
    force: bool,
) -> list[tuple[AuditorReport, Filing, Company]]:
    """Return list of (AuditorReport, Filing, Company) to classify."""
    stmt = (
        select(AuditorReport, Filing, Company)
        .join(Filing, AuditorReport.filing_id == Filing.id)
        .join(Company, Filing.company_id == Company.id)
        .where(Filing.form_type == "10-K")
        .order_by(Company.ticker, Filing.filing_date.desc())
    )

    if ticker_filter:
        stmt = stmt.where(Company.ticker.in_([t.upper() for t in ticker_filter]))

    if not force:
        # Exclude reports that already have a GoingConcernFlag
        already_classified_subq = select(GoingConcernFlag.filing_id)
        stmt = stmt.where(Filing.id.not_in(already_classified_subq))

    rows = db.execute(stmt).all()
    return [(r.AuditorReport, r.Filing, r.Company) for r in rows]


def _print_summary(
    results: list[tuple[str, str, ClassificationResult | None, str]],
    client: ClaudeClassifier,
    elapsed: float,
    dry_run: bool,
) -> None:
    detail = Table(title="Classification Summary", show_lines=False)
    detail.add_column("Ticker", style="bold")
    detail.add_column("Filing Date")
    detail.add_column("Severity")
    detail.add_column("Conf", justify="right")
    detail.add_column("Flag Type")
    detail.add_column("Model", style="dim")
    detail.add_column("Validated", justify="center")

    severity_counts: dict[str, int] = {"critical": 0, "elevated": 0, "watch": 0, "none": 0}
    validation_failures = 0
    classified = 0
    errors = 0

    for ticker, filing_date, result, error in results:
        if result is None:
            detail.add_row(ticker, filing_date, "[red]ERROR[/red]", "-", "-", "-", "ERR")
            errors += 1
            continue

        classified += 1
        sev = result.severity
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if not result.validation_passed:
            validation_failures += 1

        conf_str = f"{float(result.classification_confidence):.2f}"
        val_icon = "ok" if result.validation_passed else "[yellow]WARN[/yellow]"

        detail.add_row(
                ticker,
                filing_date,
                _SEVERITY_STYLE.get(sev, sev),
                conf_str,
                _FLAG_TYPE_STYLE.get(result.flag_type, result.flag_type),
                result.model_used[:16],  # truncate to avoid wide columns
                val_icon,
            )

    console.print()
    console.print(detail)
    console.print()

    avg_latency = elapsed / max(classified, 1)
    console.print(f"Total classified:          {classified}")
    console.print(f"Errors:                    {errors}")
    console.print(f"Severity breakdown:")
    for sev, count in severity_counts.items():
        if count:
            console.print(f"  {sev}: {count}")
    console.print(f"Validation failures:       {validation_failures}")
    console.print(f"Total cost estimate:       [bold green]${client.total_cost_estimate:.4f}[/bold green]")
    console.print(f"Avg latency per report:    {avg_latency:.1f}s")
    console.print(f"Total wall time:           {elapsed:.1f}s")

    if dry_run:
        console.print("\n[yellow]DRY RUN — no rows written to DB.[/yellow]")


def _parse_tickers(tickers_str: str | None) -> list[str] | None:
    if not tickers_str:
        return None
    return [t.strip().upper() for t in tickers_str.split(",") if t.strip()]


if __name__ == "__main__":
    app()
