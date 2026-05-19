"""add data-integrity CHECK constraints

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-17

Adds production-grade PostgreSQL CHECK constraints as defence-in-depth on top
of the application-level validation layer.  The migration pre-checks all
existing rows before applying constraints so that any violations surface as
clear errors rather than cryptic DB failures.

Constraint design notes
-----------------------
``offsets_valid`` allows the sentinel (0, 0) pair used for severity='none'
flags where no quote exists.  The alternative (NULL) would require schema
changes to the NOT-NULL columns.

``severity_quote_consistency`` allows NULL quoted_language for severity='none'
rows (the classifier writes NULL when no quote is produced).
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

logger = logging.getLogger("alembic.b2c3d4e5f6a7")

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _pre_check(conn) -> None:
    """Raise if any existing rows violate the about-to-be-added constraints."""
    checks = [
        # confidence outside [0, 1]
        (
            "going_concern_flags",
            "classification_confidence < 0 OR classification_confidence > 1",
            "confidence_in_range",
        ),
        # offsets: neither sentinel (0,0) nor valid range
        (
            "going_concern_flags",
            "NOT (char_offset_start = 0 AND char_offset_end = 0) "
            "AND NOT (char_offset_start >= 0 AND char_offset_end > char_offset_start)",
            "offsets_valid",
        ),
        # severity/quote consistency
        (
            "going_concern_flags",
            "NOT ("
            "  (severity = 'none' AND (quoted_language IS NULL OR quoted_language = '')) "
            "  OR "
            "  (severity != 'none' AND quoted_language IS NOT NULL AND char_length(quoted_language) > 0)"
            ")",
            "severity_quote_consistency",
        ),
        # CIK format
        (
            "companies",
            "cik !~ '^[0-9]{10}$'",
            "cik_is_10_digits",
        ),
        # Filing date not in the future
        (
            "filings",
            "filing_date > CURRENT_DATE",
            "filing_date_not_future",
        ),
    ]

    for table, where, constraint_name in checks:
        result = conn.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {where}")
        ).scalar()
        if result > 0:
            raise RuntimeError(
                f"Pre-check failed for '{constraint_name}': {result} rows in '{table}' "
                f"would violate the constraint. Inspect with: "
                f"SELECT * FROM {table} WHERE {where} LIMIT 10"
            )
        logger.info("Pre-check OK: %s on %s", constraint_name, table)


def upgrade() -> None:
    conn = op.get_bind()
    _pre_check(conn)

    # ── going_concern_flags ────────────────────────────────────────────────
    op.create_check_constraint(
        "confidence_in_range",
        "going_concern_flags",
        "classification_confidence >= 0.0 AND classification_confidence <= 1.0",
    )

    # Sentinel (0, 0) allowed for severity='none' rows (no quoted passage)
    op.create_check_constraint(
        "offsets_valid",
        "going_concern_flags",
        "(char_offset_start = 0 AND char_offset_end = 0) "
        "OR (char_offset_start >= 0 AND char_offset_end > char_offset_start)",
    )

    op.create_check_constraint(
        "severity_quote_consistency",
        "going_concern_flags",
        "(severity = 'none' AND (quoted_language IS NULL OR quoted_language = '')) "
        "OR "
        "(severity != 'none' AND quoted_language IS NOT NULL AND char_length(quoted_language) > 0)",
    )

    # ── companies ─────────────────────────────────────────────────────────
    op.create_check_constraint(
        "cik_is_10_digits",
        "companies",
        "cik ~ '^[0-9]{10}$'",
    )

    # ── filings ───────────────────────────────────────────────────────────
    op.create_check_constraint(
        "filing_date_not_future",
        "filings",
        "filing_date <= CURRENT_DATE",
    )


def downgrade() -> None:
    op.drop_constraint("filing_date_not_future", "filings", type_="check")
    op.drop_constraint("cik_is_10_digits", "companies", type_="check")
    op.drop_constraint("severity_quote_consistency", "going_concern_flags", type_="check")
    op.drop_constraint("offsets_valid", "going_concern_flags", type_="check")
    op.drop_constraint("confidence_in_range", "going_concern_flags", type_="check")
