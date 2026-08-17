"""
Integration tests — run the full pipeline against generated sample data
and verify outputs are produced and sensible.
"""

import csv
import os
import tempfile
import unittest
from pathlib import Path

from reporter.loader import load_files
from reporter.validate import validate, write_quarantine
from reporter.analyze import analyze
from reporter.render_md import render_md
from reporter.render_html import render_html
from reporter.render_csv import render_summary_csv


class TestFullPipeline(unittest.TestCase):
    SAMPLE = "sample_data/orders_2025.csv"

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _run_pipeline(self):
        raw = load_files(self.SAMPLE)
        result = validate(raw)
        report = analyze(
            result.valid,
            total_raw_rows=len(raw),
            quarantined_rows=len(result.quarantined),
        )
        return raw, result, report

    def test_sample_data_exists(self):
        self.assertTrue(Path(self.SAMPLE).exists(), "sample_data/orders_2025.csv not found")

    def test_pipeline_produces_valid_records(self):
        raw, result, report = self._run_pipeline()
        self.assertGreater(len(result.valid), 400)
        self.assertGreater(len(result.quarantined), 50)

    def test_quarantine_contains_all_bad_categories(self):
        raw, result, _ = self._run_pipeline()
        reasons = " ".join(q.reason for q in result.quarantined)
        self.assertIn("missing_price", reasons)
        self.assertIn("negative_price", reasons)
        self.assertIn("invalid_quantity", reasons)
        self.assertIn("future_date", reasons)
        self.assertIn("unparseable_date", reasons)
        self.assertIn("duplicate_order_id", reasons)

    def test_months_covered(self):
        _, _, report = self._run_pipeline()
        # The sample data covers Jan-Jun 2025 (6 months of clean data);
        # some dirty rows with future dates from 2026 may also pass if today >= 2026.
        self.assertGreaterEqual(report.months_covered, 6)

    def test_revenue_is_positive(self):
        _, _, report = self._run_pipeline()
        self.assertGreater(report.net_revenue, 0)

    def test_top_products_at_most_10(self):
        _, _, report = self._run_pipeline()
        self.assertLessEqual(len(report.top_products), 10)

    def test_summary_csv_written(self):
        _, _, report = self._run_pipeline()
        path = os.path.join(self.tmpdir, "summary.csv")
        render_summary_csv(report, path)
        self.assertTrue(Path(path).exists())
        with open(path) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), report.months_covered)
        self.assertIn("net_revenue", rows[0])

    def test_md_report_written(self):
        _, _, report = self._run_pipeline()
        path = os.path.join(self.tmpdir, "report.md")
        render_md(report, path)
        content = Path(path).read_text()
        self.assertIn("# Sales Report", content)
        self.assertIn("Net Revenue", content)
        self.assertIn("Top 10", content)

    def test_html_report_written(self):
        _, _, report = self._run_pipeline()
        path = os.path.join(self.tmpdir, "report.html")
        render_html(report, path)
        content = Path(path).read_text()
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("Net Revenue", content)
        # No external CDN links
        self.assertNotIn("cdn.jsdelivr.net", content)
        self.assertNotIn("unpkg.com", content)

    def test_quarantine_csv_written(self):
        raw, result, _ = self._run_pipeline()
        path = os.path.join(self.tmpdir, "quarantine.csv")
        write_quarantine(result.quarantined, path)
        self.assertTrue(Path(path).exists())
        with open(path) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), len(result.quarantined))
        self.assertIn("reason", rows[0])


if __name__ == "__main__":
    unittest.main()
