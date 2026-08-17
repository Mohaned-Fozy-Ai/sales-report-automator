"""
validate.py — Data quality gate.

Business problem: a single corrupt row (null price, future date, duplicate ID)
can silently skew a month's revenue figure by thousands of dollars. Rather than
crashing or silently dropping rows, this module quarantines bad rows with a
human-readable reason so the store owner can fix the source data.
"""

import csv
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from reporter.loader import RawRecord

logger = logging.getLogger(__name__)

REFUND_STATUSES = {"refunded", "returned", "return", "refund", "cancelled", "canceled"}


@dataclass
class ValidRecord:
    """A row that has passed all quality checks, ready for analysis."""
    order_id: str
    order_date: date
    year_month: str          # "YYYY-MM", precomputed for grouping
    product_name: str
    quantity: int
    unit_price: Decimal
    revenue: Decimal         # quantity * unit_price (negative for refunds)
    is_refund: bool
    status: Optional[str]
    source_file: str
    source_line: int


@dataclass
class QuarantinedRecord:
    """A row that failed at least one quality check."""
    order_id: str
    order_date_raw: str
    product_name: str
    quantity_raw: str
    unit_price_raw: str
    status: Optional[str]
    source_file: str
    source_line: int
    reason: str


@dataclass
class ValidationResult:
    """Output of the validation pass."""
    valid: list[ValidRecord] = field(default_factory=list)
    quarantined: list[QuarantinedRecord] = field(default_factory=list)


def validate(records: list[RawRecord], today: Optional[date] = None) -> ValidationResult:
    """
    Applies every quality rule to a list of RawRecord and splits them into
    valid and quarantined buckets.

    Why we run all checks per row (not short-circuit): a row can have multiple
    problems and it's more useful to the store owner to see all reasons at once.
    """
    if today is None:
        today = date.today()

    result = ValidationResult()
    seen_ids: dict[str, int] = {}  # order_id -> first source_line it appeared

    for rec in records:
        reasons: list[str] = []

        # --- Rule 1: missing or non-numeric unit_price ---
        if rec.unit_price is None:
            reasons.append(f"missing_price: unit_price={rec.unit_price_raw!r}")

        # --- Rule 2: negative unit_price ---
        elif rec.unit_price < Decimal("0"):
            reasons.append(f"negative_price: unit_price={rec.unit_price_raw!r}")

        # --- Rule 3: missing or non-numeric quantity ---
        if rec.quantity is None:
            reasons.append(f"invalid_quantity: quantity={rec.quantity_raw!r}")
        elif rec.quantity < 0:
            reasons.append(f"negative_quantity: quantity={rec.quantity_raw!r}")

        # --- Rule 4: unparseable date ---
        if rec.order_date is None:
            reasons.append(f"unparseable_date: order_date={rec.order_date_raw!r}")

        # --- Rule 5: future date ---
        elif rec.order_date > today:
            reasons.append(f"future_date: order_date={rec.order_date_raw!r}")

        # --- Rule 6: duplicate order ID (quarantine the second occurrence) ---
        if rec.order_id:
            if rec.order_id in seen_ids:
                reasons.append(
                    f"duplicate_order_id: first seen at line {seen_ids[rec.order_id]}"
                )
            else:
                seen_ids[rec.order_id] = rec.source_line
        else:
            reasons.append("missing_order_id")

        if reasons:
            result.quarantined.append(QuarantinedRecord(
                order_id=rec.order_id,
                order_date_raw=rec.order_date_raw,
                product_name=rec.product_name,
                quantity_raw=rec.quantity_raw,
                unit_price_raw=rec.unit_price_raw,
                status=rec.status,
                source_file=rec.source_file,
                source_line=rec.source_line,
                reason="; ".join(reasons),
            ))
        else:
            is_refund = (rec.status or "").strip().lower() in REFUND_STATUSES
            revenue = rec.unit_price * rec.quantity  # type: ignore[operator]
            if is_refund:
                revenue = -abs(revenue)

            result.valid.append(ValidRecord(
                order_id=rec.order_id,
                order_date=rec.order_date,  # type: ignore[arg-type]
                year_month=rec.order_date.strftime("%Y-%m"),  # type: ignore[union-attr]
                product_name=rec.product_name,
                quantity=rec.quantity,  # type: ignore[arg-type]
                unit_price=rec.unit_price,  # type: ignore[arg-type]
                revenue=revenue,
                is_refund=is_refund,
                status=rec.status,
                source_file=rec.source_file,
                source_line=rec.source_line,
            ))

    logger.info(
        "Validation complete: %d valid, %d quarantined",
        len(result.valid), len(result.quarantined),
    )
    return result


def write_quarantine(quarantined: list[QuarantinedRecord], path: str) -> None:
    """
    Writes quarantined rows to a CSV so the store owner can review and fix them.

    Keeping bad rows visible (rather than silently dropping) is crucial: a
    missing-price row for a $500 B2B order would silently undercount revenue.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "order_id", "order_date_raw", "product_name", "quantity_raw",
        "unit_price_raw", "status", "source_file", "source_line", "reason",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for q in quarantined:
            writer.writerow({
                "order_id": q.order_id,
                "order_date_raw": q.order_date_raw,
                "product_name": q.product_name,
                "quantity_raw": q.quantity_raw,
                "unit_price_raw": q.unit_price_raw,
                "status": q.status or "",
                "source_file": q.source_file,
                "source_line": q.source_line,
                "reason": q.reason,
            })
    logger.info("Quarantine file written: %s (%d rows)", path, len(quarantined))
