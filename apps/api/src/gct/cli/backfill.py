"""Backfill CLI — fetches SEC filings and populates the database.

Usage:
    # By ticker (the original mode)
    python -m gct.cli.backfill --tickers AAPL,MSFT --max-10k 3 --max-10q 4

    # By CIK (bypasses ticker→CIK resolution; useful for defunct/renamed companies)
    python -m gct.cli.backfill --ciks 0000886158,0001813756 --max-10k 5 --max-10q 0

    # Both at once (no duplicates — upsert is idempotent on CIK)
    python -m gct.cli.backfill --tickers AAPL --ciks 0000886158 --max-10k 3

The command is idempotent: re-running for the same companies updates existing
rows rather than creating duplicates (see persistence.py for the upsert logic).

This is a Tier-1 component: no LLM calls, no classification.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass

import typer
from rich.console import Console
from rich.table import Table

from gct.database import SessionLocal
from gct.ingestion.edgar_client import EdgarClient
from gct.ingestion.exceptions import EdgarError, TickerNotFoundError
from gct.ingestion.filing_fetcher import FetchedFiling, FilingFetcher
from gct.ingestion.filing_parser import extract_auditor_report
from gct.ingestion.persistence import (
    save_raw_html,
    upsert_auditor_report,
    upsert_company,
    upsert_filing,
)
from gct.ingestion import normalize_cik
from gct.ingestion.ticker_lookup import _clear_ticker_cache

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False)
console = Console()


@dataclass
class _CompanyResult:
    """Result for one company (identified by ticker or CIK)."""
    label: str          # ticker if known, else the raw CIK
    company_name: str = ""
    cik: str = ""
    count_10k: int = 0
    count_10q: int = 0
    auditor_reports: int = 0
    error: str | None = None


@app.command()
def backfill(
    tickers: str | None = typer.Option(
        None,
        "--tickers",
        help="Comma-separated ticker list, e.g. AAPL,MSFT",
    ),
    ciks: str | None = typer.Option(
        None,
        "--ciks",
        help=(
            "Comma-separated zero-padded 10-digit CIK list, e.g. 0000886158,0001813756. "
            "Bypasses ticker resolution — useful for defunct or renamed companies."
        ),
    ),
    max_10k: int = typer.Option(5, "--max-10k", help="Max 10-K filings per company"),
    max_10q: int = typer.Option(8, "--max-10q", help="Max 10-Q filings per company"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Backfill SEC filings for one or more tickers and/or CIKs."""
    if verbose:
        logging.getLogger("gct").setLevel(logging.INFO)

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else []

    raw_ciks = [c.strip() for c in ciks.split(",") if c.strip()] if ciks else []
    try:
        cik_list = [normalize_cik(c) for c in raw_ciks]
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1)

    if not ticker_list and not cik_list:
        console.print("[red]Error: at least one of --tickers or --ciks must be provided.[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold]Going Concern Tracker — Backfill[/bold]  "
        + (f"tickers={ticker_list}  " if ticker_list else "")
        + (f"ciks={cik_list}  " if cik_list else "")
        + f"max_10k={max_10k}  max_10q={max_10q}\n"
    )

    results = asyncio.run(_run_backfill(ticker_list, cik_list, max_10k, max_10q))
    _print_summary(results)

    if any(r.error for r in results):
        raise typer.Exit(1)


async def _run_backfill(
    ticker_list: list[str],
    cik_list: list[str],
    max_10k: int,
    max_10q: int,
) -> list[_CompanyResult]:
    """Main async backfill loop: one EdgarClient, one DB session per run."""
    _clear_ticker_cache()

    results: list[_CompanyResult] = []
    form_types = [ft for ft, cap in [("10-K", max_10k), ("10-Q", max_10q)] if cap > 0]
    max_per_type = {"10-K": max_10k, "10-Q": max_10q}

    async with EdgarClient() as client:
        fetcher = FilingFetcher(client)
        db = SessionLocal()
        try:
            # ── Ticker-based ingestion ────────────────────────────────────────
            for ticker in ticker_list:
                result = _CompanyResult(label=ticker)
                console.print(f"  [cyan]> {ticker}[/cyan]", end=" ")
                sys.stdout.flush()
                try:
                    filings = await fetcher.fetch_filings_for_company(
                        ticker=ticker,
                        form_types=form_types,
                        max_per_type=max_per_type,
                    )
                    _ingest_filings(result, filings, db)
                    console.print(
                        f"[green]ok[/green]  "
                        f"10-K={result.count_10k}  10-Q={result.count_10q}  "
                        f"reports={result.auditor_reports}"
                    )
                except TickerNotFoundError:
                    result.error = "ticker not found in SEC database"
                    console.print("[red]ticker not found[/red]")
                except EdgarError as exc:
                    result.error = str(exc)
                    console.print(f"[red]{exc}[/red]")
                except Exception as exc:
                    result.error = f"unexpected error: {exc}"
                    logger.exception("Unexpected error processing ticker %s", ticker)
                    console.print("[red]unexpected error[/red]")
                results.append(result)

            # ── CIK-based ingestion ───────────────────────────────────────────
            for cik in cik_list:
                result = _CompanyResult(label=cik)
                console.print(f"  [cyan]> CIK {cik}[/cyan]", end=" ")
                sys.stdout.flush()
                try:
                    filings = await fetcher.fetch_filings_by_cik(
                        cik=cik,
                        form_types=form_types,
                        max_per_type=max_per_type,
                    )
                    _ingest_filings(result, filings, db)
                    # Update display label to resolved ticker if available
                    if filings and filings[0].ticker:
                        result.label = filings[0].ticker
                    console.print(
                        f"[green]ok[/green]  "
                        f"10-K={result.count_10k}  10-Q={result.count_10q}  "
                        f"reports={result.auditor_reports}"
                    )
                except EdgarError as exc:
                    result.error = str(exc)
                    console.print(f"[red]{exc}[/red]")
                except Exception as exc:
                    result.error = f"unexpected error: {exc}"
                    logger.exception("Unexpected error processing CIK %s", cik)
                    console.print("[red]unexpected error[/red]")
                results.append(result)

        finally:
            db.close()

    return results


def _ingest_filings(
    result: _CompanyResult,
    filings: list[FetchedFiling],
    db,
) -> None:
    """Shared persistence logic for both ticker and CIK paths."""
    if not filings:
        result.error = "no filings returned"
        return

    first = filings[0]
    result.cik = first.cik
    result.company_name = first.company_name

    company = upsert_company(
        db,
        ticker=first.ticker,
        cik=first.cik,
        name=first.company_name,
    )
    db.commit()

    for fetched in filings:
        raw_path = save_raw_html(fetched.cik, fetched.accession_number, fetched.raw_html)
        filing = upsert_filing(db, company.id, fetched, raw_text_path=raw_path)
        db.commit()

        if fetched.form_type == "10-K":
            result.count_10k += 1
        else:
            result.count_10q += 1

        extraction = extract_auditor_report(
            fetched.raw_html,
            fetched.form_type,
            filing_id=fetched.accession_number,
        )
        if extraction is not None:
            upsert_auditor_report(db, filing.id, extraction)
            db.commit()
            result.auditor_reports += 1


def _print_summary(results: list[_CompanyResult]) -> None:
    table = Table(title="\nBackfill Summary", show_lines=False)
    table.add_column("Ticker/CIK", style="bold")
    table.add_column("Company")
    table.add_column("CIK")
    table.add_column("10-Ks", justify="right")
    table.add_column("10-Qs", justify="right")
    table.add_column("Reports", justify="right")
    table.add_column("Status")

    for r in results:
        status = "[green]ok[/green]" if r.error is None else f"[red]{r.error}[/red]"
        table.add_row(
            r.label,
            r.company_name or "-",
            r.cik or "-",
            str(r.count_10k),
            str(r.count_10q),
            str(r.auditor_reports),
            status,
        )

    console.print(table)


if __name__ == "__main__":
    app()
