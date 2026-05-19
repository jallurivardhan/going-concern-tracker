"""Populate display_name for the existing 8 companies with hand-crafted user-friendly names."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from sqlalchemy import select

from gct.database import SessionLocal
from gct.models import Company

DISPLAY_NAMES: dict[str, str] = {
    "0000886158": "Bed Bath & Beyond Inc. (pre-bankruptcy)",
    "0000320193": "Apple Inc.",
    "0001655210": "Beyond Meat, Inc.",
    "0001130713": "Beyond, Inc. (formerly Overstock)",
    "0000789019": "Microsoft Corporation",
    "0001639825": "Peloton Interactive, Inc.",
    "0001008654": "Tupperware Brands Corporation",
    "0001813756": "WeWork Inc.",
}


def main() -> None:
    s = SessionLocal()
    try:
        updated = 0
        for cik, display in DISPLAY_NAMES.items():
            c = s.execute(select(Company).where(Company.cik == cik)).scalar_one_or_none()
            if c is None:
                print(f"WARN: CIK {cik} not in database; skipping")
                continue
            c.display_name = display
            updated += 1
            print(f"  {cik}  {c.name!r:<45}  ->  {display!r}")
        s.commit()
        print(f"\nUpdated {updated} companies.")
    finally:
        s.close()


if __name__ == "__main__":
    main()
