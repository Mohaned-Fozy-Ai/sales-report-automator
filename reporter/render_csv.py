"""
render_csv.py — Machine-readable CSV summary renderer.

Business problem: the store owner may want to ingest the summarised numbers
into another system (Google Sheets, BI tool, accounting software). A clean
summary.csv with one row per month provides that integration point without
requiring them to parse the HTML report.
"""

import csv
import logging
from pathlib import Path

from reporter.analyze import ReportData

logger = logging.getLogger(__name__)


def render_summary_csv(report: ReportData, path: str) -> None:
    """Writes a machine-readable monthly summary CSV to *path*."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "year_month",
        "net_revenue",
        "order_count",
        "refund_count",
        "refund_amount",
        "avg_order_value",
        "mom_growth_pct",
    ]

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for m in report.monthly:
            writer.writerow({
                "year_month": m.year_month,
                "net_revenue": str(m.net_revenue),
                "order_count": m.order_count,
                "refund_count": m.refund_count,
                "refund_amount": str(m.refund_amount),
                "avg_order_value": str(m.avg_order_value),
                "mom_growth_pct": str(m.mom_growth_pct) if m.mom_growth_pct is not None else "",
            })

    logger.info("Summary CSV written: %s", path)
