"""Set display_name for the four 2024-2025 going-concern companies."""
from gct.database import SessionLocal
from gct.models import Company
from sqlalchemy import select

DISPLAY_NAMES = {
    "0001498710": "Spirit Airlines, Inc.",
    "0000768835": "Big Lots, Inc.",
    "0001804591": "23andMe Holding Co.",
    "0001628063": "Express, Inc.",
}

def main():
    s = SessionLocal()
    try:
        for cik, display in DISPLAY_NAMES.items():
            c = s.execute(select(Company).where(Company.cik == cik)).scalar_one_or_none()
            if c is None:
                print(f"WARN: CIK {cik} not in database; skipping")
                continue
            c.display_name = display
            print(f"  {cik}  display_name -> {display!r}")
        s.commit()
        print("Done.")
    finally:
        s.close()

if __name__ == "__main__":
    main()
