"""Verify proposed watchlist tickers against SEC EDGAR."""
import asyncio
from gct.ingestion.edgar_client import EdgarClient


FULL_INGEST_NEW = [
    "GOOGL", "AMZN", "META", "TSLA", "NVDA", "JPM", "WMT", "V", "COST", "BRK.B",
    "SFIX", "HIMS", "W", "HOOD", "SNAP", "PLUG", "CVNA", "AMCX", "RIVN", "LCID",
    "MULN", "WOLF", "HTZ", "FFIE", "FSR", "NKLA", "GOEV", "RIDE", "AMC", "GME",
]

METADATA_ONLY = [
    "AAPL", "MSFT", "GOOG", "JNJ", "UNH", "XOM", "LLY", "PG", "HD", "ABBV",
    "MA", "AVGO", "CVX", "MRK", "ORCL", "BAC", "PFE", "KO", "PEP", "DIS",
    "TMO", "ABT", "CSCO", "ADBE", "CRM", "NKE", "ACN", "MCD", "CMCSA", "DHR",
    "INTC", "VZ", "AMD", "QCOM", "IBM", "T", "TXN", "AMGN", "NEE", "BMY",
    "PM", "RTX", "HON", "LOW", "INTU", "SBUX", "GE", "BLK", "CAT", "AXP",
    "DE", "BA", "GS", "MMM", "MO", "BKNG", "ELV", "MDT", "GILD", "ADP",
]


async def verify_ticker(client, ticker_map, ticker):
    normalized = ticker.upper().replace("-", ".")
    cik = ticker_map.get(normalized) or ticker_map.get(ticker.upper())
    if not cik:
        return (ticker, None, None, "not in ticker map")
    try:
        submissions = await client.get_company_submissions(cik)
        return (ticker, cik, submissions.get("name", "Unknown"), None)
    except Exception as e:
        return (ticker, cik, None, str(e)[:80])


async def main():
    client = EdgarClient()
    print("Fetching SEC ticker map...")
    ticker_map = await client.get_ticker_cik_map()
    print(f"Ticker map size: {len(ticker_map)}")
    print()

    print("=" * 100)
    print("FULL INGEST CANDIDATES (30 tickers)")
    print("=" * 100)
    full_results = []
    for ticker in FULL_INGEST_NEW:
        result = await verify_ticker(client, ticker_map, ticker)
        full_results.append(result)
        status = "OK" if result[1] else "MISS"
        cik = result[1] or "----------"
        name = result[2] or result[3] or ""
        print(f"  [{status}] {ticker:<8} {cik:<12} {name}")

    print()
    print("=" * 100)
    print("METADATA ONLY CANDIDATES (60 tickers)")
    print("=" * 100)
    meta_results = []
    for ticker in METADATA_ONLY:
        result = await verify_ticker(client, ticker_map, ticker)
        meta_results.append(result)
        status = "OK" if result[1] else "MISS"
        cik = result[1] or "----------"
        name = result[2] or result[3] or ""
        print(f"  [{status}] {ticker:<8} {cik:<12} {name}")

    full_found = [r for r in full_results if r[1]]
    full_missing = [r for r in full_results if not r[1]]
    meta_found = [r for r in meta_results if r[1]]
    meta_missing = [r for r in meta_results if not r[1]]

    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Full ingest:    found {len(full_found)}/{len(full_results)},  missing {len(full_missing)}")
    print(f"Metadata only:  found {len(meta_found)}/{len(meta_results)}, missing {len(meta_missing)}")
    if full_missing:
        print()
        print("Missing from full ingest list:")
        for r in full_missing:
            print(f"  - {r[0]}")
    if meta_missing:
        print()
        print("Missing from metadata list:")
        for r in meta_missing:
            print(f"  - {r[0]}")

    print()
    print("=" * 100)
    print("CIKs FOR FULL-INGEST BACKFILL (paste into --ciks)")
    print("=" * 100)
    print(",".join(r[1] for r in full_found))
    print()
    print("=" * 100)
    print("METADATA-ONLY ROWS TO INSERT")
    print("=" * 100)
    for r in meta_found:
        print(f"  {r[0]:<8}  {r[1]:<12}  {r[2]}")


if __name__ == "__main__":
    asyncio.run(main())
