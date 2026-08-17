"""
Tests for reporter/analyze.py — revenue computation, rounding, anomaly detection.
"""

import unittest
from datetime import date
from decimal import Decimal

from reporter.validate import ValidRecord
from reporter.analyze import analyze, _round_money


def _make_valid(
    order_id="ORD-001",
    order_date=date(2025, 1, 15),
    year_month="2025-01",
    product_name="Widget",
    quantity=2,
    unit_price=Decimal("49.99"),
    revenue=Decimal("99.98"),
    is_refund=False,
    status="completed",
    source_file="test.csv",
    source_line=2,
):
    return ValidRecord(
        order_id=order_id,
        order_date=order_date,
        year_month=year_month,
        product_name=product_name,
        quantity=quantity,
        unit_price=unit_price,
        revenue=revenue,
        is_refund=is_refund,
        status=status,
        source_file=source_file,
        source_line=source_line,
    )


class TestRoundMoney(unittest.TestCase):
    def test_rounds_half_up(self):
        self.assertEqual(_round_money(Decimal("0.005")), Decimal("0.01"))

    def test_rounds_down(self):
        self.assertEqual(_round_money(Decimal("1.234")), Decimal("1.23"))

    def test_exact_value_unchanged(self):
        self.assertEqual(_round_money(Decimal("10.50")), Decimal("10.50"))


class TestAnalyze(unittest.TestCase):
    def _records(self, *recs):
        return list(recs)

    def test_single_order_revenue(self):
        rec = _make_valid(revenue=Decimal("99.98"))
        report = analyze([rec], total_raw_rows=1, quarantined_rows=0)
        self.assertEqual(report.net_revenue, Decimal("99.98"))
        self.assertEqual(report.total_orders, 1)

    def test_multiple_months_aggregated(self):
        jan = _make_valid(order_id="ORD-001", year_month="2025-01",
                          order_date=date(2025, 1, 10), revenue=Decimal("100.00"))
        feb = _make_valid(order_id="ORD-002", year_month="2025-02",
                          order_date=date(2025, 2, 10), revenue=Decimal("200.00"))
        report = analyze([jan, feb], total_raw_rows=2, quarantined_rows=0)
        self.assertEqual(len(report.monthly), 2)
        self.assertEqual(report.net_revenue, Decimal("300.00"))

    def test_refund_reduces_revenue(self):
        sale = _make_valid(order_id="ORD-001", revenue=Decimal("100.00"))
        refund = _make_valid(
            order_id="ORD-002",
            revenue=Decimal("-50.00"),
            is_refund=True,
            status="refunded",
        )
        report = analyze([sale, refund], total_raw_rows=2, quarantined_rows=0)
        self.assertEqual(report.net_revenue, Decimal("50.00"))
        self.assertEqual(report.total_refunds, 1)

    def test_mom_growth_computed(self):
        jan = _make_valid(order_id="ORD-001", year_month="2025-01",
                          order_date=date(2025, 1, 10), revenue=Decimal("100.00"))
        feb = _make_valid(order_id="ORD-002", year_month="2025-02",
                          order_date=date(2025, 2, 10), revenue=Decimal("150.00"))
        report = analyze([jan, feb], total_raw_rows=2, quarantined_rows=0)
        # February growth: (150-100)/100 = 50%
        self.assertEqual(report.monthly[0].mom_growth_pct, None)   # January: no prior month
        self.assertEqual(report.monthly[1].mom_growth_pct, Decimal("50.00"))

    def test_products_sorted_by_revenue(self):
        a = _make_valid(order_id="ORD-001", product_name="A", revenue=Decimal("300.00"))
        b = _make_valid(order_id="ORD-002", product_name="B", revenue=Decimal("100.00"))
        c = _make_valid(order_id="ORD-003", product_name="C", revenue=Decimal("200.00"))
        report = analyze([a, b, c], total_raw_rows=3, quarantined_rows=0)
        self.assertEqual(report.products[0].product_name, "A")
        self.assertEqual(report.products[1].product_name, "C")
        self.assertEqual(report.products[2].product_name, "B")

    def test_top_10_products_capped(self):
        recs = [
            _make_valid(
                order_id=f"ORD-{i:03d}",
                product_name=f"Prod-{i}",
                revenue=Decimal(str(i * 10)),
            )
            for i in range(1, 16)  # 15 products
        ]
        report = analyze(recs, total_raw_rows=15, quarantined_rows=0)
        self.assertEqual(len(report.top_products), 10)

    def test_anomaly_revenue_drop_detected(self):
        # Product had $200 in Jan, $100 in Feb => -50% drop (> 40%)
        recs = [
            _make_valid(order_id="ORD-001", year_month="2025-01",
                        order_date=date(2025, 1, 10),
                        product_name="Widget", revenue=Decimal("200.00")),
            _make_valid(order_id="ORD-002", year_month="2025-02",
                        order_date=date(2025, 2, 10),
                        product_name="Widget", revenue=Decimal("100.00")),
        ]
        report = analyze(recs, total_raw_rows=2, quarantined_rows=0)
        drop_anomalies = [a for a in report.anomalies if a.kind == "revenue_drop"]
        self.assertGreater(len(drop_anomalies), 0)

    def test_no_anomaly_for_small_drop(self):
        # Only 10% drop — should not trigger
        recs = [
            _make_valid(order_id="ORD-001", year_month="2025-01",
                        order_date=date(2025, 1, 10),
                        product_name="Widget", revenue=Decimal("100.00")),
            _make_valid(order_id="ORD-002", year_month="2025-02",
                        order_date=date(2025, 2, 10),
                        product_name="Widget", revenue=Decimal("90.00")),
        ]
        report = analyze(recs, total_raw_rows=2, quarantined_rows=0)
        drop_anomalies = [a for a in report.anomalies if a.kind == "revenue_drop"]
        self.assertEqual(len(drop_anomalies), 0)

    def test_high_value_order_anomaly_detected(self):
        # One order is way above the others — should trigger 3-sigma check
        recs = [
            _make_valid(order_id=f"ORD-{i:03d}", product_name="Widget",
                        revenue=Decimal("50.00"))
            for i in range(1, 30)
        ]
        # Add one extreme outlier
        recs.append(_make_valid(
            order_id="ORD-999",
            product_name="Widget",
            revenue=Decimal("50000.00"),
        ))
        report = analyze(recs, total_raw_rows=31, quarantined_rows=0)
        hv_anomalies = [a for a in report.anomalies if a.kind == "high_value_order"]
        self.assertGreater(len(hv_anomalies), 0)

    def test_avg_order_value_money_precision(self):
        # 3 orders totalling $100.01 — AOV should be Decimal, not float
        recs = [
            _make_valid(order_id="ORD-001", revenue=Decimal("33.34")),
            _make_valid(order_id="ORD-002", revenue=Decimal("33.34")),
            _make_valid(order_id="ORD-003", revenue=Decimal("33.33")),
        ]
        report = analyze(recs, total_raw_rows=3, quarantined_rows=0)
        # Should be Decimal type (not float)
        self.assertIsInstance(report.avg_order_value, Decimal)
        # And should be rounded to 2 dp
        self.assertEqual(report.avg_order_value, Decimal("33.34"))

    def test_empty_records_does_not_crash(self):
        report = analyze([], total_raw_rows=0, quarantined_rows=0)
        self.assertEqual(report.total_orders, 0)
        self.assertEqual(report.net_revenue, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
