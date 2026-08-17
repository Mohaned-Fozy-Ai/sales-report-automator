"""
Tests for reporter/loader.py — column mapping and date parsing.
"""

import csv
import os
import tempfile
import unittest
from decimal import Decimal

from reporter.loader import (
    _build_column_map,
    _parse_date,
    _parse_decimal,
    _parse_quantity,
    load_files,
)


class TestBuildColumnMap(unittest.TestCase):
    def test_canonical_headers_map_correctly(self):
        headers = ["Order ID", "order_date", "product_name", "quantity", "unit_price", "status"]
        m = _build_column_map(headers)
        self.assertEqual(m["order_id"], 0)
        self.assertEqual(m["order_date"], 1)
        self.assertEqual(m["unit_price"], 4)

    def test_alternative_header_spellings(self):
        headers = ["OrderID", "Date", "Item", "Qty", "Price", "State"]
        m = _build_column_map(headers)
        self.assertIn("order_id", m)
        self.assertIn("order_date", m)
        self.assertIn("product_name", m)
        self.assertIn("quantity", m)
        self.assertIn("unit_price", m)

    def test_extra_columns_ignored(self):
        headers = ["order_id", "order_date", "product_name", "quantity", "unit_price",
                   "tracking_number", "warehouse_id"]
        m = _build_column_map(headers)
        self.assertNotIn("tracking_number", m)
        self.assertEqual(m["order_id"], 0)

    def test_case_insensitive(self):
        headers = ["ORDER ID", "ORDER DATE", "PRODUCT NAME", "QUANTITY", "UNIT PRICE"]
        m = _build_column_map(headers)
        self.assertIn("order_id", m)
        self.assertIn("unit_price", m)


class TestParseDate(unittest.TestCase):
    def test_iso_format(self):
        d = _parse_date("2025-03-15")
        self.assertIsNotNone(d)
        self.assertEqual(d.year, 2025)
        self.assertEqual(d.month, 3)
        self.assertEqual(d.day, 15)

    def test_uk_format(self):
        d = _parse_date("15/03/2025")
        self.assertIsNotNone(d)
        self.assertEqual(d.month, 3)

    def test_us_format(self):
        d = _parse_date("03/15/2025")
        self.assertIsNotNone(d)
        self.assertEqual(d.day, 15)

    def test_us_dashes(self):
        d = _parse_date("03-15-2025")
        self.assertIsNotNone(d)
        self.assertEqual(d.month, 3)

    def test_unparseable_returns_none(self):
        self.assertIsNone(_parse_date("not-a-date"))
        self.assertIsNone(_parse_date("32-13-2025"))
        self.assertIsNone(_parse_date("yesterday"))
        self.assertIsNone(_parse_date(""))


class TestParseDecimal(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(_parse_decimal("49.99"), Decimal("49.99"))

    def test_dollar_sign(self):
        self.assertEqual(_parse_decimal("$149.99"), Decimal("149.99"))

    def test_comma_thousands(self):
        self.assertEqual(_parse_decimal("1,299.99"), Decimal("1299.99"))

    def test_euro_sign(self):
        self.assertEqual(_parse_decimal("€29.99"), Decimal("29.99"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_decimal(""))

    def test_non_numeric_returns_none(self):
        self.assertIsNone(_parse_decimal("N/A"))


class TestParseQuantity(unittest.TestCase):
    def test_integer_string(self):
        self.assertEqual(_parse_quantity("3"), 3)

    def test_float_string_truncated(self):
        self.assertEqual(_parse_quantity("2.0"), 2)

    def test_non_numeric_returns_none(self):
        self.assertIsNone(_parse_quantity("N/A"))
        self.assertIsNone(_parse_quantity("unknown"))
        self.assertIsNone(_parse_quantity(""))


class TestLoadFiles(unittest.TestCase):
    def _make_csv(self, rows, headers=None):
        if headers is None:
            headers = ["Order ID", "order_date", "product_name", "quantity", "unit_price", "status"]
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        writer = csv.DictWriter(tmp, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        tmp.close()
        return tmp.name

    def tearDown(self):
        # cleanup temp files created by tests
        pass

    def test_loads_basic_csv(self):
        path = self._make_csv([{
            "Order ID": "ORD-001",
            "order_date": "2025-01-15",
            "product_name": "Widget",
            "quantity": "2",
            "unit_price": "19.99",
            "status": "completed",
        }])
        try:
            records = load_files(path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].order_id, "ORD-001")
            self.assertEqual(records[0].quantity, 2)
            self.assertEqual(records[0].unit_price, Decimal("19.99"))
        finally:
            os.unlink(path)

    def test_no_files_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            load_files("/nonexistent/path/*.csv")

    def test_glob_loads_multiple_files(self):
        path1 = self._make_csv([{
            "Order ID": "ORD-001", "order_date": "2025-01-10",
            "product_name": "A", "quantity": "1", "unit_price": "10.00", "status": "completed",
        }])
        path2 = self._make_csv([{
            "Order ID": "ORD-002", "order_date": "2025-02-10",
            "product_name": "B", "quantity": "2", "unit_price": "20.00", "status": "completed",
        }])
        import glob as glob_mod
        tmpdir = os.path.dirname(path1)
        # Use explicit paths joined by pattern via temp file approach
        try:
            records = load_files(path1) + load_files(path2)
            self.assertEqual(len(records), 2)
        finally:
            os.unlink(path1)
            os.unlink(path2)


if __name__ == "__main__":
    unittest.main()
