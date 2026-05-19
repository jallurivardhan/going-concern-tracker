"""Tests for gct.cli.refresh."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from gct.cli.refresh import _load_watchlist, app


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def watchlist_yaml(tmp_path: Path) -> Path:
    content = """
version: "1.0"
companies:
  - cik: "0000886158"
    note: "Bed Bath & Beyond"
  - cik: "0001813756"
    note: "WeWork"
"""
    p = tmp_path / "watchlist.yaml"
    p.write_text(content)
    return p


class TestLoadWatchlist:
    def test_returns_normalised_ciks(self, watchlist_yaml: Path):
        ciks = _load_watchlist(watchlist_yaml)
        assert ciks == ["0000886158", "0001813756"]

    def test_empty_watchlist(self, tmp_path: Path):
        p = tmp_path / "empty.yaml"
        p.write_text("version: '1.0'\ncompanies: []\n")
        assert _load_watchlist(p) == []

    def test_bom_prefixed_yaml_loads_correctly(self, tmp_path: Path):
        """UTF-8 BOM written by Windows editors must be stripped before YAML parse."""
        content = "version: '1.0'\ncompanies:\n  - cik: '0000886158'\n    note: 'test'\n"
        bom_path = tmp_path / "bom_watchlist.yaml"
        # Write with explicit BOM prefix
        bom_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        ciks = _load_watchlist(bom_path)
        assert ciks == ["0000886158"]


class TestRefreshCreatesPipelineRun:
    """Smoke test: the refresh command creates a PipelineRun row."""

    def _make_session(self):
        db = MagicMock()
        # PipelineRun refresh call
        run = MagicMock()
        run.id = uuid.uuid4()
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = datetime.now(timezone.utc)
        run.status = "success"
        run.filings_checked = 0
        run.filings_new = 0
        run.filings_classified = 0
        run.flags_created = 0
        run.total_cost_estimate = Decimal("0")
        run.trigger = "manual"

        db.execute.return_value.scalar_one.return_value = run
        db.execute.return_value.scalar_one_or_none.return_value = None
        db.execute.return_value.all.return_value = []
        return db, run

    def test_run_created_and_committed(self, runner, watchlist_yaml: Path):
        db, run = self._make_session()

        with (
            patch("gct.cli.refresh.SessionLocal", return_value=db),
            patch("gct.cli.refresh._fetch_all", new_callable=lambda: lambda *a, **k: _async_noop()),
            patch("gct.cli.refresh._classify_unclassified", new_callable=lambda: lambda *a, **k: _async_return_zero()),
        ):
            result = runner.invoke(app, ["--watchlist", str(watchlist_yaml), "--trigger", "manual"])

        # Should have added a PipelineRun and committed
        db.add.assert_called_once()
        assert db.commit.called
        assert result.exit_code == 0


class TestRefreshOnlyNewFilings:
    """Verify that filings already in the DB are not re-ingested."""

    def test_skips_existing_accessions(self, watchlist_yaml: Path):
        from gct.cli.refresh import _accession_exists

        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = MagicMock()  # non-None = exists

        assert _accession_exists(db, "0000886158-23-000123") is True

    def test_new_accession_not_in_db(self, watchlist_yaml: Path):
        from gct.cli.refresh import _accession_exists

        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None

        assert _accession_exists(db, "0000886158-99-000999") is False


class TestRefreshHandlesPerFilingErrors:
    """A per-company error should not abort the whole run."""

    def test_fetch_error_is_collected_not_raised(self, runner, watchlist_yaml: Path):
        db = MagicMock()
        run = MagicMock()
        run.id = uuid.uuid4()
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = datetime.now(timezone.utc)
        run.status = "success"
        run.filings_checked = 0
        run.filings_new = 0
        run.filings_classified = 0
        run.flags_created = 0
        run.total_cost_estimate = Decimal("0")
        run.trigger = "manual"

        db.execute.return_value.scalar_one.return_value = run
        db.execute.return_value.scalar_one_or_none.return_value = None
        db.execute.return_value.all.return_value = []

        async def _failing_fetch_all(cik_list, max_10k, db, errors, run_id):
            errors.append({"cik": cik_list[0], "phase": "fetch", "message": "simulated EDGAR error"})

        with (
            patch("gct.cli.refresh.SessionLocal", return_value=db),
            patch("gct.cli.refresh._fetch_all", side_effect=_failing_fetch_all),
            patch("gct.cli.refresh._classify_unclassified", new_callable=lambda: lambda *a, **k: _async_return_zero()),
        ):
            result = runner.invoke(app, ["--watchlist", str(watchlist_yaml), "--trigger", "manual"])

        # Run should complete, not crash
        assert result.exit_code == 0


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _async_noop(*args, **kwargs):
    pass


async def _async_return_zero(*args, **kwargs):
    return (0, 0, Decimal("0"))
