"""
analyze.py — Pure analytical computation layer.

Business problem: computing correct month-over-month growth, finding anomalous
orders, and ranking products are all error-prone when done manually in a
spreadsheet with copy-pasted formulas. This module does it once, correctly,
with Decimal arithmetic and no side effects, so results are reproducible.
"""

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from reporter.validate import ValidRecord

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    """Rounds to 2 decimal places using banker's-rounding (ROUND_HALF_UP for finance)."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass
class MonthStats:
    year_month: str
    revenue: Decimal
    order_count: int
    refund_count: int
    refund_amount: Decimal
    net_revenue: Decimal
    avg_order_value: Decimal
    mom_growth_pct: Optional[Decimal]   # None for first month


@dataclass
class ProductStats:
    product_name: str
    total_revenue: Decimal
    total_units: int
    order_count: int


@dataclass
class Anomaly:
    kind: str    # "revenue_drop" or "high_value_order"
    description: str
    detail: str


@dataclass
class ReportData:
    """Complete analytical output — passed to renderers."""
    # Scalar KPIs
    total_revenue: Decimal
    total_orders: int
    total_refunds: int
    total_refund_amount: Decimal
    net_revenue: Decimal
    avg_order_value: Decimal
    date_range_start: str
    date_range_end: str
    months_covered: int

    # Detailed breakdowns
    monthly: list[MonthStats]
    products: list[ProductStats]           # all products, sorted by revenue desc
    top_products: list[ProductStats]       # top 10

    # Anomalies
    anomalies: list[Anomaly]

    # Meta
    total_raw_rows: int
    valid_rows: int
    quarantined_rows: int


def analyze(
    records: list[ValidRecord],
    total_raw_rows: int,
    quarantined_rows: int,
) -> ReportData:
    """
    Transforms a list of validated records into a fully computed ReportData.

    Why pure function with no I/O: makes the module trivially testable —
    you pass in records, get back a dataclass, no file system involved.
    """
    if not records:
        logger.warning("analyze() called with zero valid records")

    # ------------------------------------------------------------------ #
    # Monthly aggregation
    # ------------------------------------------------------------------ #
    monthly_revenue: dict[str, Decimal] = defaultdict(Decimal)
    monthly_orders: dict[str, int] = defaultdict(int)
    monthly_refunds: dict[str, int] = defaultdict(int)
    monthly_refund_amt: dict[str, Decimal] = defaultdict(Decimal)

    for rec in records:
        ym = rec.year_month
        if rec.is_refund:
            monthly_refunds[ym] += 1
            monthly_refund_amt[ym] += abs(rec.revenue)
            monthly_revenue[ym] += rec.revenue  # revenue is already negative
        else:
            monthly_revenue[ym] += rec.revenue
            monthly_orders[ym] += 1

    all_months = sorted(set(monthly_revenue) | set(monthly_orders))

    monthly_stats: list[MonthStats] = []
    prev_net: Optional[Decimal] = None

    for ym in all_months:
        rev = _round_money(monthly_revenue.get(ym, Decimal("0")))
        ref_amt = _round_money(monthly_refund_amt.get(ym, Decimal("0")))
        net = _round_money(rev)  # revenue already incorporates negative refunds
        orders = monthly_orders.get(ym, 0)
        refunds = monthly_refunds.get(ym, 0)
        total_txn = orders + refunds

        aov = _round_money(net / total_txn) if total_txn else Decimal("0")

        if prev_net is not None and prev_net != Decimal("0"):
            growth = _round_money((net - prev_net) / abs(prev_net) * 100)
        else:
            growth = None

        monthly_stats.append(MonthStats(
            year_month=ym,
            revenue=rev,
            order_count=orders,
            refund_count=refunds,
            refund_amount=ref_amt,
            net_revenue=net,
            avg_order_value=aov,
            mom_growth_pct=growth,
        ))
        prev_net = net

    # ------------------------------------------------------------------ #
    # Product aggregation
    # ------------------------------------------------------------------ #
    prod_revenue: dict[str, Decimal] = defaultdict(Decimal)
    prod_units: dict[str, int] = defaultdict(int)
    prod_orders: dict[str, int] = defaultdict(int)

    for rec in records:
        pn = rec.product_name
        prod_revenue[pn] += rec.revenue
        prod_units[pn] += rec.quantity
        prod_orders[pn] += 1

    product_stats = sorted(
        [
            ProductStats(
                product_name=pn,
                total_revenue=_round_money(prod_revenue[pn]),
                total_units=prod_units[pn],
                order_count=prod_orders[pn],
            )
            for pn in prod_revenue
        ],
        key=lambda p: p.total_revenue,
        reverse=True,
    )

    top_products = product_stats[:10]

    # ------------------------------------------------------------------ #
    # Scalar KPIs
    # ------------------------------------------------------------------ #
    total_revenue = _round_money(sum(monthly_revenue.values(), Decimal("0")))
    total_orders = sum(monthly_orders.values())
    total_refunds = sum(monthly_refunds.values())
    total_refund_amount = _round_money(sum(monthly_refund_amt.values(), Decimal("0")))
    net_revenue = _round_money(total_revenue)

    total_txn = total_orders + total_refunds
    avg_order_value = _round_money(net_revenue / total_txn) if total_txn else Decimal("0")

    dates = sorted(rec.order_date for rec in records)
    date_start = dates[0].isoformat() if dates else "N/A"
    date_end = dates[-1].isoformat() if dates else "N/A"

    # ------------------------------------------------------------------ #
    # Anomaly detection
    # ------------------------------------------------------------------ #
    anomalies: list[Anomaly] = []

    # --- Anomaly 1: product revenue drop > 40% month-over-month ---
    prod_monthly: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for rec in records:
        prod_monthly[rec.product_name][rec.year_month] += rec.revenue

    for pname, monthly_map in prod_monthly.items():
        sorted_months = sorted(monthly_map.keys())
        for i in range(1, len(sorted_months)):
            prev_m = sorted_months[i - 1]
            curr_m = sorted_months[i]
            prev_r = monthly_map[prev_m]
            curr_r = monthly_map[curr_m]
            if prev_r > Decimal("0"):
                change = (curr_r - prev_r) / prev_r * 100
                if change < Decimal("-40"):
                    anomalies.append(Anomaly(
                        kind="revenue_drop",
                        description=f"{pname}: revenue dropped {_round_money(change)}% from {prev_m} to {curr_m}",
                        detail=(
                            f"Previous: ${_round_money(prev_r):,}  "
                            f"Current: ${_round_money(curr_r):,}"
                        ),
                    ))

    # --- Anomaly 2: orders more than 3 SD above the mean value ---
    order_values = [float(rec.revenue) for rec in records if not rec.is_refund and rec.revenue > 0]
    if len(order_values) >= 2:
        mean_val = statistics.mean(order_values)
        stdev_val = statistics.stdev(order_values)
        threshold = mean_val + 3 * stdev_val
        for rec in records:
            if not rec.is_refund and float(rec.revenue) > threshold:
                anomalies.append(Anomaly(
                    kind="high_value_order",
                    description=(
                        f"Order {rec.order_id} ({rec.product_name}): "
                        f"${_round_money(rec.revenue):,} is >{_round_money(Decimal(str(threshold))):,} "
                        f"(mean + 3σ threshold)"
                    ),
                    detail=f"Date: {rec.order_date}  Source: {rec.source_file}:{rec.source_line}",
                ))

    logger.info(
        "Analysis complete: net_revenue=%s, %d months, %d products, %d anomalies",
        net_revenue, len(monthly_stats), len(product_stats), len(anomalies),
    )

    return ReportData(
        total_revenue=total_revenue,
        total_orders=total_orders,
        total_refunds=total_refunds,
        total_refund_amount=total_refund_amount,
        net_revenue=net_revenue,
        avg_order_value=avg_order_value,
        date_range_start=date_start,
        date_range_end=date_end,
        months_covered=len(monthly_stats),
        monthly=monthly_stats,
        products=product_stats,
        top_products=top_products,
        anomalies=anomalies,
        total_raw_rows=total_raw_rows,
        valid_rows=len(records),
        quarantined_rows=quarantined_rows,
    )
