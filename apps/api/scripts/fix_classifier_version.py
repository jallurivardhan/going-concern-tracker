"""Fix classifier_version strings that have a doubled 'claude' prefix.

Before: "v1.0-claude-claude-haiku-4-5"  (CLASSIFIER_VERSION was "v1.0-claude")
After:  "v1.0-claude-haiku-4-5"         (CLASSIFIER_VERSION is now "v1.0")

Run once after updating prompts.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from sqlalchemy import text

from gct.database import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT classifier_version, COUNT(*) AS cnt "
            "FROM going_concern_flags "
            "GROUP BY classifier_version"
        )).all()
        print("Before:")
        for ver, cnt in rows:
            print(f"  {cnt:>3}x  {ver!r}")

        result = db.execute(text(
            "UPDATE going_concern_flags "
            "SET classifier_version = REPLACE(classifier_version, 'v1.0-claude-claude-', 'v1.0-claude-') "
            "WHERE classifier_version LIKE 'v1.0-claude-claude-%'"
        ))
        db.commit()
        print(f"\nUpdated {result.rowcount} rows.")

        rows_after = db.execute(text(
            "SELECT classifier_version, COUNT(*) AS cnt "
            "FROM going_concern_flags "
            "GROUP BY classifier_version"
        )).all()
        print("\nAfter:")
        for ver, cnt in rows_after:
            print(f"  {cnt:>3}x  {ver!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
