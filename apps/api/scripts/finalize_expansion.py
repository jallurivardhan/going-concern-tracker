"""
Final expansion step:
1. Insert metadata-only Company rows for 60 S&P 100 picks
2. Set good display names for the 23 newly-ingested companies
3. Override AMC Networks display name (legal name shows incorrectly in EDGAR)
"""
from gct.database import SessionLocal
from gct.models import Company
from sqlalchemy import select
from uuid import uuid4

METADATA_ONLY = [
    ("0000320193", "AAPL",  "Apple Inc."),
    ("0000789019", "MSFT",  "Microsoft Corporation"),
    ("0001652044", "GOOG",  "Alphabet Inc. (Class C)"),
    ("0000200406", "JNJ",   "Johnson & Johnson"),
    ("0000731766", "UNH",   "UnitedHealth Group"),
    ("0000034088", "XOM",   "Exxon Mobil Corporation"),
    ("0000059478", "LLY",   "Eli Lilly and Company"),
    ("0000080424", "PG",    "Procter & Gamble"),
    ("0000354950", "HD",    "The Home Depot"),
    ("0001551152", "ABBV",  "AbbVie Inc."),
    ("0001141391", "MA",    "Mastercard Incorporated"),
    ("0001730168", "AVGO",  "Broadcom Inc."),
    ("0000093410", "CVX",   "Chevron Corporation"),
    ("0000310158", "MRK",   "Merck & Co."),
    ("0001341439", "ORCL",  "Oracle Corporation"),
    ("0000070858", "BAC",   "Bank of America"),
    ("0000078003", "PFE",   "Pfizer Inc."),
    ("0000021344", "KO",    "The Coca-Cola Company"),
    ("0000077476", "PEP",   "PepsiCo Inc."),
    ("0001744489", "DIS",   "The Walt Disney Company"),
    ("0000097745", "TMO",   "Thermo Fisher Scientific"),
    ("0000001800", "ABT",   "Abbott Laboratories"),
    ("0000858877", "CSCO",  "Cisco Systems"),
    ("0000796343", "ADBE",  "Adobe Inc."),
    ("0001108524", "CRM",   "Salesforce Inc."),
    ("0000320187", "NKE",   "Nike Inc."),
    ("0001467373", "ACN",   "Accenture plc"),
    ("0000063908", "MCD",   "McDonald's Corporation"),
    ("0001166691", "CMCSA", "Comcast Corporation"),
    ("0000313616", "DHR",   "Danaher Corporation"),
    ("0000050863", "INTC",  "Intel Corporation"),
    ("0000732712", "VZ",    "Verizon Communications"),
    ("0000002488", "AMD",   "Advanced Micro Devices"),
    ("0000804328", "QCOM",  "Qualcomm Inc."),
    ("0000051143", "IBM",   "International Business Machines"),
    ("0000732717", "T",     "AT&T Inc."),
    ("0000097476", "TXN",   "Texas Instruments"),
    ("0000318154", "AMGN",  "Amgen Inc."),
    ("0000753308", "NEE",   "NextEra Energy"),
    ("0000014272", "BMY",   "Bristol Myers Squibb"),
    ("0001413329", "PM",    "Philip Morris International"),
    ("0000101829", "RTX",   "RTX Corporation"),
    ("0000773840", "HON",   "Honeywell International"),
    ("0000060667", "LOW",   "Lowe's Companies"),
    ("0000896878", "INTU",  "Intuit Inc."),
    ("0000829224", "SBUX",  "Starbucks Corporation"),
    ("0000040545", "GE",    "General Electric"),
    ("0002012383", "BLK",   "BlackRock Inc."),
    ("0000018230", "CAT",   "Caterpillar Inc."),
    ("0000004962", "AXP",   "American Express"),
    ("0000315189", "DE",    "Deere & Company"),
    ("0000012927", "BA",    "The Boeing Company"),
    ("0000886982", "GS",    "The Goldman Sachs Group"),
    ("0000066740", "MMM",   "3M Company"),
    ("0000764180", "MO",    "Altria Group"),
    ("0001075531", "BKNG",  "Booking Holdings"),
    ("0001156039", "ELV",   "Elevance Health"),
    ("0001613103", "MDT",   "Medtronic plc"),
    ("0000882095", "GILD",  "Gilead Sciences"),
    ("0000008670", "ADP",   "Automatic Data Processing"),
]

FULL_INGEST_DISPLAY_NAMES = {
    "0001652044": "Alphabet Inc.",
    "0001018724": "Amazon.com Inc.",
    "0001326801": "Meta Platforms, Inc.",
    "0001318605": "Tesla, Inc.",
    "0001045810": "NVIDIA Corporation",
    "0000019617": "JPMorgan Chase & Co.",
    "0000104169": "Walmart Inc.",
    "0001403161": "Visa Inc.",
    "0000909832": "Costco Wholesale Corporation",
    "0001576942": "Stitch Fix, Inc.",
    "0001773751": "Hims & Hers Health, Inc.",
    "0001616707": "Wayfair Inc.",
    "0001783879": "Robinhood Markets, Inc.",
    "0001564408": "Snap Inc.",
    "0001093691": "Plug Power Inc.",
    "0001690820": "Carvana Co.",
    "0001514991": "AMC Networks Inc.",
    "0001874178": "Rivian Automotive, Inc.",
    "0001811210": "Lucid Group, Inc.",
    "0000895419": "Wolfspeed, Inc.",
    "0001657853": "Hertz Global Holdings",
    "0001411579": "AMC Entertainment Holdings",
    "0001326380": "GameStop Corp.",
}


def main():
    s = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for cik, ticker, display in METADATA_ONLY:
            existing = s.execute(select(Company).where(Company.cik == cik)).scalar_one_or_none()
            if existing:
                if not existing.display_name:
                    existing.display_name = display
                skipped += 1
                continue
            new_company = Company(
                id=uuid4(),
                cik=cik,
                ticker=ticker,
                name=display,
                display_name=display,
            )
            s.add(new_company)
            inserted += 1
            print(f"  + inserted {ticker:<6} {cik}  {display}")
        s.commit()
        print(f"\nMetadata-only: {inserted} new rows inserted, {skipped} already existed.")
        print()

        updated = 0
        for cik, display in FULL_INGEST_DISPLAY_NAMES.items():
            c = s.execute(select(Company).where(Company.cik == cik)).scalar_one_or_none()
            if c is None:
                print(f"  ! CIK {cik} not found in DB; skipping")
                continue
            old = c.display_name
            c.display_name = display
            updated += 1
            print(f"  ~ {cik}  display_name {old!r} -> {display!r}")
        s.commit()
        print(f"\nDisplay names: {updated} updated.")

        total = s.query(Company).count()
        print()
        print("=" * 70)
        print(f"Total companies in database: {total}")
        print("=" * 70)
    finally:
        s.close()


if __name__ == "__main__":
    main()
