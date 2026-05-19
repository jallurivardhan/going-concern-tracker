"""Custom exception hierarchy for the ingestion pipeline.

Keeping these separate from FastAPI HTTP exceptions lets the CLI and background
workers catch them without importing any web-framework code.
"""


class EdgarError(Exception):
    """Base class for all SEC EDGAR ingestion errors."""


class TickerNotFoundError(EdgarError):
    """Raised when a ticker symbol cannot be resolved to a CIK after a fresh fetch."""

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"Ticker '{ticker}' not found in the SEC EDGAR ticker database.")


class FilingFetchError(EdgarError):
    """Raised when fetching a specific filing document fails after retries."""

    def __init__(self, accession_number: str, reason: str) -> None:
        self.accession_number = accession_number
        self.reason = reason
        super().__init__(
            f"Failed to fetch filing {accession_number}: {reason}"
        )


class ParseError(EdgarError):
    """Raised when an unexpected structural problem prevents parsing a filing."""

    def __init__(self, accession_number: str, reason: str) -> None:
        self.accession_number = accession_number
        self.reason = reason
        super().__init__(
            f"Parse error for filing {accession_number}: {reason}"
        )
