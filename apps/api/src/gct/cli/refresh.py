"""Continuous ingestion CLI — refresh pipeline.

Reads the watchlist, fetches new 10-K filings from SEC EDGAR, parses auditor
reports, classifies them, and records metadata in pipeline_runs.

Usage:
    python -m gct.cli.refresh
    python -m gct.cli.refresh --trigger manual
    python -m gct.cli.refresh --watchlist apps/api/data/watchlist.yaml
    python -m gct.cli.refresh --max-10k 2
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from gct.classifier.classifier import classify_auditor_report
from gct.classifier.claude_client import ClaudeClassifier
from gct.config import settings
from gct.database import SessionLocal
from gct.ingestion import normalize_cik
from gct.ingestion.edgar_client import EdgarClient
from gct.ingestion.filing_fetcher import FilingFetcher
from gct.ingestion.filing_parser import extract_auditor_report
from gct.ingestion.persistence import (
    save_raw_html,
    upsert_auditor_report,
    upsert_company,
    upsert_filing,
)
from gct.models import AuditorReport, Company, Filing, GoingConcernFlag, PipelineRun

logging.basicConfig(level=logging.WARNING, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False)
console = Console()

_DEFAULT_WATCHLIST = Path(__file__).parents[3] / "data" / "watchlist.yaml"


def _load_watchlist(path: Path) -> list[str]:
    """Return list of normalised CIKs from the watchlist YAML.

    Uses ``utf-8-sig`` encoding so that UTF-8 BOM bytes written by Windows
    text editors are transparently stripped before YAML parsing.
    """
    with open(path, encoding="utf-8-sig") as f:
        data = yaml.safe_load(f)
    return [normalize_cik(entry["cik"]) for entry in data.get("companies", [])]


def _get_latest_filing_date(db, cik: str):
    """Return the most recent filing_date we have for a company, or None."""
    result = db.execute(
        select(Filing.filing_date)
        .join(Company, Filing.company_id == Company.id)
        .where(Company.cik == cik, Filing.form_type == "10-K")
        .order_by(Filing.filing_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    return result


def _accession_exists(db, accession_number: str) -> bool:
    return db.execute(
        select(Filing.id).where(Filing.accession_number == accession_number).limit(1)
    ).scalar_one_or_none() is not None


@app.command()
def refresh(
    watchlist: Path = typer.Option(
        _DEFAULT_WATCHLIST,
        "--watchlist",
        help="Path to watchlist YAML",
        exists=True,
    ),
    max_10k: int = typer.Option(3, "--max-10k", help="Max 10-K filings fetched per company"),
    trigger: str = typer.Option("manual", "--trigger", help="'scheduled' or 'manual'"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Refresh pipeline: fetch new filings → parse → classify → record run."""
    if verbose:
        logging.getLogger("gct").setLevel(logging.INFO)

    console.print(f"\n[bold]Going Concern Tracker — Refresh Pipeline[/bold]  trigger={trigger}\n")

    db = SessionLocal()
    try:
        # ── 1. Create PipelineRun row ─────────────────────────────────────────
        run = PipelineRun(
            id=uuid.uuid4(),
            started_at=datetime.now(timezone.utc),
            status="running",
            trigger=trigger,
        )
        db.add(run)
        db.commit()
        run_id = run.id
        console.print(f"  Pipeline run ID: {run_id}\n")

        errors: list[dict[str, Any]] = []
        filings_checked = 0
        filings_new = 0

        # ── 2. Load watchlist ─────────────────────────────────────────────────
        cik_list = _load_watchlist(watchlist)
        console.print(f"  Watchlist: {len(cik_list)} companies\n")

        # ── 3. Fetch new filings for each CIK ────────────────────────────────
        asyncio.run(_fetch_all(cik_list, max_10k, db, errors, run_id))

        # Re-read counters after async phase (db state may have changed)
        db.refresh(run)
        filings_new = run.filings_new
        filings_checked = run.filings_checked

        # ── 4. Classify unclassified reports ──────────────────────────────────
        filings_classified, flags_created, total_cost = asyncio.run(
            _classify_unclassified(db, errors)
        )

        # ── 5. Update PipelineRun ──────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        run.completed_at = now
        run.filings_classified = filings_classified
        run.flags_created = flags_created
        run.total_cost_estimate = total_cost
        run.errors = errors if errors else None
        run.status = "success" if not errors else "partial_success"
        db.commit()

        _print_summary(run, errors)

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        try:
            run.status = "failure"
            run.completed_at = datetime.now(timezone.utc)
            run.errors = [{"type": "pipeline_failure", "message": str(exc)}]
            db.commit()
        except Exception:
            pass
        console.print(f"[red]Pipeline failed: {exc}[/red]")
        raise typer.Exit(1)
    finally:
        db.close()


async def _fetch_all(
    cik_list: list[str],
    max_10k: int,
    db,
    errors: list[dict],
    run_id: uuid.UUID,
) -> None:
    """Fetch new 10-K filings for all CIKs in the watchlist."""
    filings_checked = 0
    filings_new = 0

    async with EdgarClient() as client:
        fetcher = FilingFetcher(client)

        for cik in cik_list:
            console.print(f"  [cyan]> CIK {cik}[/cyan]", end=" ")
            try:
                latest_date = _get_latest_filing_date(db, cik)
                filings = await fetcher.fetch_filings_by_cik(
                    cik=cik,
                    form_types=["10-K"],
                    max_per_type={"10-K": max_10k},
                )
                filings_checked += len(filings)

                new_count = 0
                for fetched in filings:
                    # Skip if we already have this accession
                    if _accession_exists(db, fetched.accession_number):
                        continue
                    # Skip if the filing is older than our latest (shouldn't happen normally)
                    if latest_date and fetched.filing_date <= latest_date:
                        continue

                    raw_path = save_raw_html(
                        fetched.cik, fetched.accession_number, fetched.raw_html
                    )
                    company = upsert_company(
                        db,
                        ticker=fetched.ticker,
                        cik=fetched.cik,
                        name=fetched.company_name,
                    )
                    db.commit()
                    filing = upsert_filing(db, company.id, fetched, raw_text_path=raw_path)
                    db.commit()

                    extraction = extract_auditor_report(
                        fetched.raw_html,
                        fetched.form_type,
                        filing_id=fetched.accession_number,
                    )
                    if extraction is not None:
                        upsert_auditor_report(db, filing.id, extraction)
                        db.commit()

                    new_count += 1
                    filings_new += 1

                console.print(
                    f"[green]ok[/green]  checked={len(filings)}  new={new_count}"
                )

            except Exception as exc:
                logger.error("Error fetching CIK %s: %s", cik, exc)
                errors.append({"cik": cik, "phase": "fetch", "message": str(exc)})
                console.print(f"[red]error: {exc}[/red]")

    # Update counters on the run row
    run = db.execute(select(PipelineRun).where(PipelineRun.id == run_id)).scalar_one()
    run.filings_checked = filings_checked
    run.filings_new = filings_new
    db.commit()


async def _classify_unclassified(
    db,
    errors: list[dict],
) -> tuple[int, int, Decimal]:
    """Classify all AuditorReport rows that don't yet have a GoingConcernFlag."""
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

    already_classified = select(GoingConcernFlag.filing_id)
    stmt = (
        select(AuditorReport, Filing)
        .join(Filing, AuditorReport.filing_id == Filing.id)
        .where(
            Filing.form_type == "10-K",
            Filing.id.not_in(already_classified),
        )
    )
    rows = db.execute(stmt).all()

    classified = 0
    flags_created = 0

    if not rows:
        console.print("\n  No unclassified reports — nothing to classify.\n")
        return 0, 0, Decimal("0")

    console.print(f"\n  Classifying {len(rows)} unclassified report(s)...\n")

    for row in rows:
        report, filing = row.AuditorReport, row.Filing
        try:
            result = await classify_auditor_report(
                session=db,
                auditor_report_id=report.id,
                client=client,
                force=False,
            )
            db.commit()
            classified += 1
            if result and result.severity != "none":
                flags_created += 1
            console.print(
                f"    classified {filing.accession_number}  severity={result.severity if result else '?'}"
            )
        except Exception as exc:
            db.rollback()
            logger.error("Classification failed for %s: %s", filing.accession_number, exc)
            errors.append({
                "accession": filing.accession_number,
                "phase": "classify",
                "message": str(exc),
            })

    return classified, flags_created, Decimal(str(client.total_cost_estimate))


def _print_summary(run: PipelineRun, errors: list[dict]) -> None:
    duration = (
        (run.completed_at - run.started_at).total_seconds()
        if run.completed_at
        else 0
    )

    table = Table(title="\nPipeline Run Summary", show_lines=False)
    table.add_column("Field")
    table.add_column("Value")

    table.add_row("Status", f"[green]{run.status}[/green]" if run.status == "success" else f"[yellow]{run.status}[/yellow]")
    table.add_row("Duration", f"{duration:.1f}s")
    table.add_row("Filings checked", str(run.filings_checked))
    table.add_row("Filings new", str(run.filings_new))
    table.add_row("Reports classified", str(run.filings_classified))
    table.add_row("Flags created", str(run.flags_created))
    table.add_row("LLM cost estimate", f"${float(run.total_cost_estimate):.4f}")
    table.add_row("Errors", str(len(errors)))

    console.print(table)

    if errors:
        console.print("\n[yellow]Errors:[/yellow]")
        for e in errors:
            console.print(f"  • {e}")


if __name__ == "__main__":
    app()
