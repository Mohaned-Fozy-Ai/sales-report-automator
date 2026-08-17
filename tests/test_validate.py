"""
Tests for reporter/validate.py — all data quality rules.
"""

import unittest
from datetime import date
from decimal import Decimal

from reporter.loader import RawRecord
from reporter.validate import validate, REFUND_STATUSES


def _make_raw(
    order_id="ORD-001",
    order_date_raw="2025-01-15",
    order_date=date(2025, 1, 15),
    product_name="Widget",
    quantity_raw="2",
    quantity=2,
    unit_price_raw="49.99",
    unit_price=Decimal("49.99"),
    status="completed",
    source_file="test.csv",
    source_line=2,
):
    return RawRecord(
        order_id=order_id,
        order_date_raw=order_date_raw,
        order_date=order_date,
        product_name=product_name,
        quantity_raw=quantity_raw,
        quantity=quantity,
        unit_price_raw=unit_price_raw,
        unit_price=unit_price,
        status=status,
        source_file=source_file,
        source_line=source_line,
    )


class TestValidationRules(unittest.TestCase):
    TODAY = date(2025, 6, 30)

    def _validate(self, records):
        return validate(records, today=self.TODAY)

    def test_clean_row_passes(self):
        result = self._validate([_make_raw()])
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(len(result.quarantined), 0)

    def test_missing_price_quarantined(self):
        rec = _make_raw(unit_price=None, unit_price_raw="")
        result = self._validate([rec])
        self.assertEqual(len(result.quarantined), 1)
        self.assertIn("missing_price", result.quarantined[0].reason)

    def test_negative_price_quarantined(self):
        rec = _make_raw(unit_price=Decimal("-49.99"), unit_price_raw="-49.99")
        result = self._validate([rec])
        self.assertEqual(len(result.quarantined), 1)
        self.assertIn("negative_price", result.quarantined[0].reason)

    def test_non_numeric_quantity_quarantined(self):
        rec = _make_raw(quantity=None, quantity_raw="N/A")
        result = self._validate([rec])
        self.assertEqual(len(result.quarantined), 1)
        self.assertIn("invalid_quantity", result.quarantined[0].reason)

    def test_future_date_quarantined(self):
        rec = _make_raw(
            order_date=date(2026, 1, 1),
            order_date_raw="2026-01-01",
        )
        result = self._validate([rec])
        self.assertEqual(len(result.quarantined), 1)
        self.assertIn("future_date", result.quarantined[0].reason)

    def test_unparseable_date_quarantined(self):
        rec = _make_raw(order_date=None, order_date_raw="not-a-date")
        result = self._validate([rec])
        self.assertEqual(len(result.quarantined), 1)
        self.assertIn("unparseable_date", result.quarantined[0].reason)

    def test_duplicate_order_id_quarantined(self):
        rec1 = _make_raw(order_id="ORD-001", source_line=2)
        rec2 = _make_raw(order_id="ORD-001", source_line=3)
        result = self._validate([rec1, rec2])
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(len(result.quarantined), 1)
        self.assertIn("duplicate_order_id", result.quarantined[0].reason)

    def test_missing_order_id_quarantined(self):
        rec = _make_raw(order_id="")
        result = self._validate([rec])
        self.assertEqual(len(result.quarantined), 1)
        self.assertIn("missing_order_id", result.quarantined[0].reason)

    def test_refund_status_sets_is_refund(self):
        rec = _make_raw(status="refunded")
        result = self._validate([rec])
        self.assertEqual(len(result.valid), 1)
        self.assertTrue(result.valid[0].is_refund)

    def test_return_status_sets_is_refund(self):
        rec = _make_raw(status="returned")
        result = self._validate([rec])
        self.assertTrue(result.valid[0].is_refund)

    def test_refund_revenue_is_negative(self):
        rec = _make_raw(status="refunded", unit_price=Decimal("50.00"), quantity=2)
        result = self._validate([rec])
        self.assertLess(result.valid[0].revenue, 0)

    def test_normal_revenue_is_positive(self):
        rec = _make_raw(status="completed", unit_price=Decimal("30.00"), quantity=3)
        result = self._validate([rec])
        self.assertEqual(result.valid[0].revenue, Decimal("90.00"))

    def test_year_month_computed_correctly(self):
        rec = _make_raw(order_date=date(2025, 3, 22), order_date_raw="2025-03-22")
        result = self._validate([rec])
        self.assertEqual(result.valid[0].year_month, "2025-03")

    def test_row_with_multiple_errors_has_all_reasons(self):
        rec = _make_raw(
            unit_price=None, unit_price_raw="",
            quantity=None, quantity_raw="bad",
            order_date=None, order_date_raw="garbage",
        )
        result = self._validate([rec])
        reason = result.quarantined[0].reason
        self.assertIn("missing_price", reason)
        self.assertIn("invalid_quantity", reason)
        self.assertIn("unparseable_date", reason)


if __name__ == "__main__":
    unittest.main()
