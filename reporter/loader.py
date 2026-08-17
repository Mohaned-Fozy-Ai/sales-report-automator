"""
loader.py — Tolerant CSV ingestion layer.

Business problem: real export CSVs from Shopify, WooCommerce, and home-grown
systems all use different column names and date formats. A fragile loader that
requires exact headers means the tool breaks the first time a client upgrades
their platform. This module absorbs that variance so the rest of the pipeline
never has to worry about it.
"""

import csv
import glob
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column alias map — extend this dict to support more export formats.
# Keys are the canonical field names used throughout the pipeline.
# Values are lists of header spellings recognised (case-insensitive).
# ---------------------------------------------------------------------------
COLUMN_ALIASES: dict[str, list[str]] = {
    "order_id":     ["order id", "order_id", "orderid", "id", "order #", "order#"],
    "order_date":   ["order date", "order_date", "orderdate", "date", "created_at", "created at", "purchase_date"],
    "product_name": ["product name", "product_name", "productname", "item", "item name", "product", "description"],
    "quantity":     ["quantity", "qty", "units", "count", "amount", "quantity ordered"],
    "unit_price":   ["unit price", "unit_price", "unitprice", "price", "price per unit", "rate", "unit cost"],
    "status":       ["status", "order status", "order_status", "state"],
}

# Date format patterns to try, in order of specificity.
_DATE_FORMATS = [
    "%Y-%m-%d",    # ISO 8601: 2025-01-15
    "%d/%m/%Y",    # UK/EU: 15/01/2025
    "%m/%d/%Y",    # US: 01/15/2025
    "%m-%d-%Y",    # US dashes: 01-15-2025
    "%d-%m-%Y",    # EU dashes: 15-01-2025
    "%Y/%m/%d",    # ISO slashes: 2025/01/15
    "%d.%m.%Y",    # European dots: 15.01.2025
    "%B %d, %Y",   # Long: January 15, 2025
    "%b %d, %Y",   # Short month: Jan 15, 2025
]


@dataclass
class RawRecord:
    """One order row after column mapping but before validation."""
    order_id: str
    order_date_raw: str          # kept for quarantine reporting
    order_date: Optional[date]   # None means unparseable
    product_name: str
    quantity_raw: str            # kept for quarantine reporting
    quantity: Optional[int]      # None means non-numeric
    unit_price_raw: str
    unit_price: Optional[Decimal]
    status: Optional[str]
    source_file: str
    source_line: int


def _build_column_map(headers: list[str]) -> dict[str, int]:
    """
    Maps canonical field names to column indices given a CSV header row.

    Why not just raise on unknown headers: extra columns (e.g. 'tracking_number')
    are silently ignored so the user doesn't have to clean their export first.
    """
    normalised = [h.strip().lower() for h in headers]
    mapping: dict[str, int] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalised:
                mapping[canonical] = normalised.index(alias)
                break
    return mapping


def _parse_date(raw: str) -> Optional[date]:
    """
    Tries every known date format; returns None if all fail.

    Why not dateutil.parser: keeps the dependency list at zero and makes the
    parsing logic explicit, which is easier to audit for a client.
    """
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return date(*[int(x) for x in re.split(r'[-/.]', raw)][:0]) or \
                   __import__('datetime').datetime.strptime(raw, fmt).date()
        except (ValueError, TypeError):
            pass
    # Second pass using strptime directly (catches named months)
    for fmt in _DATE_FORMATS:
        try:
            import datetime
            return datetime.datetime.strptime(raw, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _parse_decimal(raw: str) -> Optional[Decimal]:
    """
    Parses a money string to Decimal, stripping currency symbols.

    Using Decimal (not float) because floating-point rounding errors accumulate
    when summing thousands of order amounts — a known pain point for finance reports.
    """
    cleaned = raw.strip().lstrip("$£€¥").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_quantity(raw: str) -> Optional[int]:
    """Returns None for non-numeric quantities (e.g. 'N/A', 'unknown')."""
    cleaned = raw.strip()
    try:
        val = float(cleaned)
        return int(val)
    except (ValueError, TypeError):
        return None


def load_files(pattern: str) -> list[RawRecord]:
    """
    Loads all CSV files matching a glob pattern into a flat list of RawRecord.

    Supports multiple files so a client can drop an entire exports folder
    rather than manually merging months before running the tool.
    """
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No CSV files matched pattern: {pattern!r}")

    logger.info("Found %d file(s) matching %r", len(paths), pattern)
    all_records: list[RawRecord] = []

    for path in paths:
        records = _load_single(path)
        logger.info("  %s -> %d rows", path, len(records))
        all_records.extend(records)

    logger.info("Total raw records loaded: %d", len(all_records))
    return all_records


def _load_single(path: str) -> list[RawRecord]:
    """Parses one CSV file, applying column mapping and type coercion."""
    records: list[RawRecord] = []
    fname = Path(path).name

    with open(path, newline="", encoding="utf-8-sig") as fh:
        # Sniff dialect (handles semicolon-delimited exports too)
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(fh, dialect)
        try:
            raw_headers = next(reader)
        except StopIteration:
            logger.warning("Empty file: %s", path)
            return records

        col_map = _build_column_map(raw_headers)
        missing = [c for c in ("order_id", "order_date", "product_name", "quantity", "unit_price")
                   if c not in col_map]
        if missing:
            logger.warning("File %s is missing required columns: %s", path, missing)

        for line_num, row in enumerate(reader, start=2):
            def get(canonical: str) -> str:
                idx = col_map.get(canonical)
                if idx is None or idx >= len(row):
                    return ""
                return row[idx].strip()

            order_date_raw = get("order_date")
            quantity_raw = get("quantity")
            unit_price_raw = get("unit_price")

            records.append(RawRecord(
                order_id=get("order_id"),
                order_date_raw=order_date_raw,
                order_date=_parse_date(order_date_raw),
                product_name=get("product_name"),
                quantity_raw=quantity_raw,
                quantity=_parse_quantity(quantity_raw),
                unit_price_raw=unit_price_raw,
                unit_price=_parse_decimal(unit_price_raw),
                status=get("status") or None,
                source_file=fname,
                source_line=line_num,
            ))

    return records
