# Tier 1 — deterministic SEC EDGAR ingestion pipeline.
# No LLM calls in this package. Results are fully reproducible given the same EDGAR filing.


def normalize_cik(raw: str) -> str:
    """Normalize a CIK to a 10-digit zero-padded string.

    Accepts any of:
        '886158'          -> '0000886158'
        '0000886158'      -> '0000886158'  (already correct)
        'CIK886158'       -> '0000886158'  (strip optional prefix)
        'CIK0000886158'   -> '0000886158'
        '  886158  '      -> '0000886158'  (leading/trailing whitespace)
        '0000000000'      -> '0000000000'  (all-zero edge case)

    Raises:
        ValueError: if the value is not numeric after stripping the optional
                    'CIK' prefix and whitespace.
    """
    cleaned = raw.strip().upper()
    if cleaned.startswith("CIK"):
        cleaned = cleaned[3:]
    # Reject empty input before any further processing
    if not cleaned:
        raise ValueError(f"Invalid CIK: {raw!r}")
    # Strip leading zeros, but keep at least one digit so "0000000000" -> "0" -> re-pad
    stripped = cleaned.lstrip("0") or "0"
    if not stripped.isdigit():
        raise ValueError(f"Invalid CIK: {raw!r}")
    return stripped.zfill(10)
