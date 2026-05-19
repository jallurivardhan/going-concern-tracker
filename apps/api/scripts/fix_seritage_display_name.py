"""Fix the wrong display_name on 0001628063 (Seritage, not Express)."""
from gct.database import SessionLocal
from gct.models import Company
from sqlalchemy import select

def main():
    s = SessionLocal()
    try:
        c = s.execute(select(Company).where(Company.cik == "0001628063")).scalar_one_or_none()
        if c is None:
            print("CIK 0001628063 not found.")
            return
        old = c.display_name
        c.display_name = "Seritage Growth Properties"
        s.commit()
        print(f"  0001628063  display_name {old!r} -> 'Seritage Growth Properties'")
    finally:
        s.close()

if __name__ == "__main__":
    main()
