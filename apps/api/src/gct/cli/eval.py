"""Evaluation CLI — run the accuracy benchmark against the golden eval set.

Usage:
    python -m gct.cli.eval                          # pretty Rich output
    python -m gct.cli.eval --json                   # machine-readable JSON
    python -m gct.cli.eval --save-report path.json  # save full report to file
    python -m gct.cli.eval --strict                 # exit 1 if below thresholds

Thresholds (--strict):
    precision >= 0.90
    recall    >= 0.80
    zero cases without a DB match
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gct.eval.benchmark import (
    ALL_SEVERITIES,
    POSITIVE_SEVERITIES,
    BenchmarkReport,
    CaseResult,
    run_benchmark,
)

app = typer.Typer(add_completion=False)
console = Console()

_STRICT_PRECISION_THRESHOLD = 0.90
_STRICT_RECALL_THRESHOLD = 0.80

_DEFAULT_EVAL_SET = Path(__file__).parents[3] / "eval" / "golden_set.json"
_DEFAULT_REPORTS_DIR = Path(__file__).parents[3] / "eval" / "reports"


@app.command()
def eval_cmd(
    eval_set: str = typer.Option(
        str(_DEFAULT_EVAL_SET),
        "--eval-set",
        help="Path to golden_set.json",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Machine-readable JSON output"
    ),
    save_report: str | None = typer.Option(
        None,
        "--save-report",
        help="Save full BenchmarkReport JSON to this path (default: eval/reports/<timestamp>.json)",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit code 1 if precision<0.90, recall<0.80, or any cases without DB match",
    ),
) -> None:
    """Run the accuracy benchmark against the hand-labeled eval set."""
    report = run_benchmark(eval_set_path=eval_set)

    # ── Determine save path ──────────────────────────────────────────────────
    if save_report is not None:
        report_path = Path(save_report)
    else:
        _DEFAULT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        report_path = _DEFAULT_REPORTS_DIR / f"{ts}.json"

    _save_report_json(report, report_path)

    # ── Output ───────────────────────────────────────────────────────────────
    if json_output:
        print(report.model_dump_json(indent=2))
    else:
        _print_report(report)
        console.print(f"\n[dim]Full report saved to: {report_path}[/dim]")

    # ── Strict mode gate ─────────────────────────────────────────────────────
    if strict:
        fail = False
        prec = float(report.precision)
        rec = float(report.recall)
        if prec < _STRICT_PRECISION_THRESHOLD:
            console.print(
                f"[red]STRICT FAIL: precision={prec:.4f} < {_STRICT_PRECISION_THRESHOLD}[/red]"
            )
            fail = True
        if rec < _STRICT_RECALL_THRESHOLD:
            console.print(
                f"[red]STRICT FAIL: recall={rec:.4f} < {_STRICT_RECALL_THRESHOLD}[/red]"
            )
            fail = True
        if report.cases_without_db_match > 0:
            console.print(
                f"[red]STRICT FAIL: {report.cases_without_db_match} case(s) have no DB match[/red]"
            )
            fail = True
        if fail:
            raise typer.Exit(code=1)


# ── Formatting helpers ────────────────────────────────────────────────────────


def _save_report_json(report: BenchmarkReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _print_report(report: BenchmarkReport) -> None:
    console.print()
    console.print(
        Panel(
            f"[bold]Going Concern Tracker — Accuracy Benchmark[/bold]\n"
            f"Eval set version:     {report.eval_set_version}\n"
            f"Classifier version:   {report.classifier_version}\n"
            f"Run timestamp:        {report.timestamp.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Total cases:          {report.total_cases}\n"
            f"Cases with DB match:  {report.cases_with_db_match}  "
            f"[{'green' if report.cases_without_db_match == 0 else 'red'}]"
            f"({report.cases_without_db_match} missing)[/{'green' if report.cases_without_db_match == 0 else 'red'}]",
            title="Benchmark Header",
            expand=False,
        )
    )

    # ── Confusion matrix ─────────────────────────────────────────────────────
    cm_table = Table(title="Confusion Matrix (rows=expected, cols=predicted)", show_lines=True)
    cm_table.add_column("Expected \\ Predicted", style="bold")
    for sev in ALL_SEVERITIES:
        cm_table.add_column(f"pred_{sev}", justify="right")
    cm_table.add_column("row_total", justify="right", style="dim")

    for exp_sev in ALL_SEVERITIES:
        row_data = report.confusion_matrix.get(exp_sev, {})
        row_vals = [str(row_data.get(pred, 0)) for pred in ALL_SEVERITIES]
        row_total = sum(row_data.get(pred, 0) for pred in ALL_SEVERITIES)
        cm_table.add_row(f"act_{exp_sev}", *row_vals, str(row_total))

    console.print(cm_table)

    # ── Metrics summary ──────────────────────────────────────────────────────
    def _fmt(d) -> str:
        return f"{float(d):.4f}"

    metrics = Table(title="Binary Metrics (positive = critical | elevated | watch)", show_lines=False)
    metrics.add_column("Metric", style="bold")
    metrics.add_column("Value", justify="right")

    metrics.add_row("True Positives", str(report.true_positives))
    metrics.add_row("True Negatives", str(report.true_negatives))
    metrics.add_row("False Positives", str(report.false_positives))
    metrics.add_row("False Negatives", str(report.false_negatives))
    metrics.add_row("Precision", _fmt(report.precision))
    metrics.add_row("Recall", _fmt(report.recall))
    metrics.add_row("F1", _fmt(report.f1))
    metrics.add_row("Accuracy", _fmt(report.accuracy))
    metrics.add_row("Avg conf (correct)", _fmt(report.avg_confidence_when_correct))
    metrics.add_row("Avg conf (wrong)", _fmt(report.avg_confidence_when_wrong))

    console.print(metrics)

    # ── Failed cases ─────────────────────────────────────────────────────────
    failed = [cr for cr in report.case_results if not cr.matches_expected]
    if failed:
        fail_table = Table(title=f"Failed Cases ({len(failed)})", show_lines=True)
        fail_table.add_column("case_id", style="bold red")
        fail_table.add_column("expected")
        fail_table.add_column("actual")
        fail_table.add_column("notes")
        for cr in failed:
            fail_table.add_row(
                cr.case_id,
                cr.expected_severity,
                cr.actual_severity or "(missing)",
                cr.notes,
            )
        console.print(fail_table)
    else:
        console.print("[green]All cases match expected labels — zero failed cases.[/green]")

    # ── Quote verification ────────────────────────────────────────────────────
    positive_cases = [
        cr for cr in report.case_results
        if cr.expected_severity in POSITIVE_SEVERITIES
    ]
    if positive_cases:
        quote_table = Table(title="Quote Verification (positive cases)", show_lines=True)
        quote_table.add_column("case_id", style="bold")
        quote_table.add_column("expected phrase", max_width=35)
        quote_table.add_column("found", justify="center")
        for cr in positive_cases:
            found_str = "[green]yes[/green]" if cr.quote_contains_expected else "[red]NO[/red]"
            quote_table.add_row(
                cr.case_id,
                (cr.expected_quoted_phrase or "")[:35],
                found_str,
            )
        console.print(quote_table)

    # ── Footer ────────────────────────────────────────────────────────────────
    if report.cases_without_db_match > 0:
        console.print(
            "\n[yellow]Some eval-set cases have no DB match. "
            "Run `python -m gct.cli.classify` to classify new filings.[/yellow]"
        )
    if failed:
        console.print(
            "\n[red]Accuracy regression detected. "
            "Review failed cases and update the classifier or the eval set.[/red]"
        )


if __name__ == "__main__":
    app()
