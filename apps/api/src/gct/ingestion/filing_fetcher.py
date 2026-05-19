"""Orchestrates per-company filing retrieval from SEC EDGAR.

For a given ticker, this module:
  1. Resolves the CIK via the SEC ticker map.
  2. Fetches the company's submission history.
  3. Selects the N most recent filings of each requested form type.
  4. Downloads the primary document HTML for each selected filing.

All data is returned as ``FetchedFiling`` Pydantic models so callers
(persistence layer, parser, CLI) work with a typed interface.

SEC EDGAR data lineage:
  Submissions API: https://data.sec.gov/submissions/CIK{cik}.json
  Filing documents: https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from pydantic import BaseModel

from gct.ingestion.edgar_client import EdgarClient, _accession_no_dashes, _cik_as_int_str
from gct.ingestion.exceptions import FilingFetchError, ParseError
from gct.ingestion.ticker_lookup import resolve_ticker_to_cik

logger = logging.getLogger(__name__)

_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# Default fetch limits (conservative for demo/backfill use)
DEFAULT_MAX_PER_TYPE: dict[str, int] = {"10-K": 5, "10-Q": 8}


class FetchedFiling(BaseModel):
    """Typed container for a filing fetched from EDGAR.

    ``raw_html`` holds the full HTML of the primary filing document.
    It is stored to disk by the persistence layer so re-extraction never
    requires a second network call.

    ``ticker`` is None when the company was ingested by CIK and the SEC
    submissions API reports no active tickers (e.g. post-bankruptcy companies).
    """

    ticker: str | None = None
    cik: str
    company_name: str
    form_type: str
    accession_number: str
    filing_date: date
    period_of_report: date | None
    filing_url: str
    raw_html: str


class FilingFetcher:
    """Fetches and assembles ``FetchedFiling`` objects for one company."""

    def __init__(self, client: EdgarClient) -> None:
        self._client = client

    async def fetch_filings_for_company(
        self,
        ticker: str,
        form_types: list[str] | None = None,
        max_per_type: dict[str, int] | None = None,
    ) -> list[FetchedFiling]:
        """Return up to ``max_per_type[form]`` most-recent filings for each form type.

        Args:
            ticker: Stock ticker, e.g. "AAPL".
            form_types: List of form types to retrieve, e.g. ["10-K", "10-Q"].
            max_per_type: Per-form-type caps, e.g. {"10-K": 5, "10-Q": 8}.

        Returns:
            List of ``FetchedFiling`` objects, sorted newest-first within each form type.
        """
        if form_types is None:
            form_types = list(DEFAULT_MAX_PER_TYPE.keys())
        if max_per_type is None:
            max_per_type = DEFAULT_MAX_PER_TYPE

        cik = await resolve_ticker_to_cik(ticker, self._client)
        if cik is None:
            logger.warning("Ticker %s not found in SEC database; skipping", ticker)
            return []

        submissions = await self._client.get_company_submissions(cik)
        company_name: str = submissions.get("name", ticker)

        recent: dict[str, Any] = submissions.get("filings", {}).get("recent", {})
        # NOTE: Companies with very long histories may have additional pages under
        # submissions["filings"]["files"].  We currently only process the "recent"
        # page (last ~1000 filings), which is sufficient for the 5/8 cap.

        accession_numbers: list[str] = recent.get("accessionNumber", [])
        filing_dates_raw: list[str] = recent.get("filingDate", [])
        report_dates_raw: list[str] = recent.get("reportDate", [])
        forms: list[str] = recent.get("form", [])
        primary_docs: list[str] = recent.get("primaryDocument", [])

        results: list[FetchedFiling] = []

        for form_type in form_types:
            cap = max_per_type.get(form_type, 5)
            fetched_count = 0

            for i, form in enumerate(forms):
                if fetched_count >= cap:
                    break
                if form != form_type:
                    continue

                acc_raw = accession_numbers[i]
                # Normalise accession number: EDGAR stores as "0000320193-24-000123"
                accession_number = acc_raw.replace("-", "")
                accession_number = f"{accession_number[:10]}-{accession_number[10:12]}-{accession_number[12:]}"

                filing_date = _parse_date(filing_dates_raw[i])
                period_of_report = _parse_date(report_dates_raw[i]) if report_dates_raw[i] else None
                primary_doc = primary_docs[i]

                cik_int = _cik_as_int_str(cik)
                acc_nodashes = _accession_no_dashes(accession_number)
                filing_url = f"{_ARCHIVES_BASE}/{cik_int}/{acc_nodashes}/{primary_doc}"

                logger.info(
                    "Fetching %s %s for %s (%s)", form_type, accession_number, ticker, filing_date
                )

                try:
                    raw_html = await self._client.get_filing_document(cik, accession_number, primary_doc)
                except FilingFetchError as exc:
                    logger.error(
                        "Skipping %s %s: %s", ticker, accession_number, exc
                    )
                    continue

                results.append(
                    FetchedFiling(
                        ticker=ticker.upper(),
                        cik=cik,
                        company_name=company_name,
                        form_type=form_type,
                        accession_number=accession_number,
                        filing_date=filing_date,
                        period_of_report=period_of_report,
                        filing_url=filing_url,
                        raw_html=raw_html,
                    )
                )
                fetched_count += 1

        logger.info(
            "Fetched %d filings for %s (CIK %s)", len(results), ticker, cik
        )
        return results

    async def fetch_filings_by_cik(
        self,
        cik: str,
        form_types: list[str] | None = None,
        max_per_type: dict[str, int] | None = None,
    ) -> list[FetchedFiling]:
        """Like ``fetch_filings_for_company`` but accepts a raw CIK string directly.

        Skips ticker→CIK resolution entirely.  The primary ticker (if any) is
        extracted from the SEC submissions API response and stored in
        ``FetchedFiling.ticker``; if the company has no active tickers (e.g. it
        went bankrupt) the field is set to ``None``.

        Args:
            cik:          Zero-padded 10-digit CIK, e.g. "0000886158".
            form_types:   Form types to retrieve.
            max_per_type: Per-form-type caps.
        """
        if form_types is None:
            form_types = list(DEFAULT_MAX_PER_TYPE.keys())
        if max_per_type is None:
            max_per_type = DEFAULT_MAX_PER_TYPE

        submissions = await self._client.get_company_submissions(cik)
        company_name: str = submissions.get("name", cik)

        # Extract the primary ticker from the submissions API response.
        # The "tickers" field is a list, e.g. ["AAPL"] or [] for defunct cos.
        raw_tickers: list[str] = submissions.get("tickers", [])
        primary_ticker: str | None = raw_tickers[0].upper() if raw_tickers else None

        recent: dict[str, Any] = submissions.get("filings", {}).get("recent", {})

        accession_numbers: list[str] = recent.get("accessionNumber", [])
        filing_dates_raw: list[str] = recent.get("filingDate", [])
        report_dates_raw: list[str] = recent.get("reportDate", [])
        forms: list[str] = recent.get("form", [])
        primary_docs: list[str] = recent.get("primaryDocument", [])

        results: list[FetchedFiling] = []

        for form_type in form_types:
            cap = max_per_type.get(form_type, 5)
            fetched_count = 0

            for i, form in enumerate(forms):
                if fetched_count >= cap:
                    break
                if form != form_type:
                    continue

                acc_raw = accession_numbers[i]
                accession_number = acc_raw.replace("-", "")
                accession_number = (
                    f"{accession_number[:10]}-{accession_number[10:12]}-{accession_number[12:]}"
                )

                filing_date = _parse_date(filing_dates_raw[i])
                period_of_report = (
                    _parse_date(report_dates_raw[i]) if report_dates_raw[i] else None
                )
                primary_doc = primary_docs[i]

                cik_int = _cik_as_int_str(cik)
                acc_nodashes = _accession_no_dashes(accession_number)
                filing_url = f"{_ARCHIVES_BASE}/{cik_int}/{acc_nodashes}/{primary_doc}"

                logger.info(
                    "Fetching %s %s for CIK %s (%s)", form_type, accession_number, cik, filing_date
                )

                try:
                    raw_html = await self._client.get_filing_document(
                        cik, accession_number, primary_doc
                    )
                except FilingFetchError as exc:
                    logger.error("Skipping CIK %s %s: %s", cik, accession_number, exc)
                    continue

                results.append(
                    FetchedFiling(
                        ticker=primary_ticker,
                        cik=cik,
                        company_name=company_name,
                        form_type=form_type,
                        accession_number=accession_number,
                        filing_date=filing_date,
                        period_of_report=period_of_report,
                        filing_url=filing_url,
                        raw_html=raw_html,
                    )
                )
                fetched_count += 1

        logger.info(
            "Fetched %d filings by CIK %s (ticker=%s)", len(results), cik, primary_ticker
        )
        return results


def _parse_date(date_str: str) -> date:
    """Parse an ISO-format date string from EDGAR (YYYY-MM-DD)."""
    return date.fromisoformat(date_str)
