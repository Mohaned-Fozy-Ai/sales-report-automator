"""
cli.py — Command-line entry point.

Business problem: the tool must run with a single command from the terminal.
This module wires together all pipeline stages, configures logging, handles
errors gracefully, and provides a --demo mode so anyone can see results
immediately without providing their own data.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from reporter.loader import load_files
from reporter.validate import validate, write_quarantine
from reporter.analyze import analyze
from reporter.render_md import render_md
from reporter.render_html import render_html
from reporter.render_csv import render_summary_csv

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "output"
DEMO_PATTERN = "sample_data/*.csv"


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run(
    pattern: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    verbose: bool = False,
) -> None:
    """
    Full pipeline: load -> validate -> analyze -> render (CSV + MD + HTML).
    This function is importable so tests can drive it without subprocess calls.
    """
    t0 = time.perf_counter()

    # 1. Load
    print(f"Loading: {pattern}")
    raw = load_files(pattern)
    total_raw = len(raw)

    # 2. Validate
    print(f"Validating {total_raw:,} rows ...")
    result = validate(raw)
    valid = result.valid
    quarantined = result.quarantined

    quarantine_path = str(Path(output_dir) / "quarantine.csv")
    if quarantined:
        write_quarantine(quarantined, quarantine_path)
        print(f"  Quarantined {len(quarantined):,} rows -> {quarantine_path}")
    else:
        print("  No rows quarantined.")

    if not valid:
        print("ERROR: No valid rows remain after validation. Check your input data.")
        sys.exit(1)

    print(f"  {len(valid):,} rows passed validation.")

    # 3. Analyse
    print("Analysing ...")
    report = analyze(valid, total_raw_rows=total_raw, quarantined_rows=len(quarantined))

    # 4. Render
    summary_path = str(Path(output_dir) / "summary.csv")
    md_path = str(Path(output_dir) / "report.md")
    html_path = str(Path(output_dir) / "report.html")

    render_summary_csv(report, summary_path)
    render_md(report, md_path)
    render_html(report, html_path)

    elapsed = time.perf_counter() - t0
    rows_per_sec = int(total_raw / elapsed) if elapsed > 0 else 0

    print()
    print("=" * 60)
    print("  REPORT COMPLETE")
    print("=" * 60)
    print(f"  Source rows   : {total_raw:,}")
    print(f"  Valid         : {len(valid):,}")
    print(f"  Quarantined   : {len(quarantined):,}")
    print(f"  Net Revenue   : ${report.net_revenue:,}")
    print(f"  Total Orders  : {report.total_orders:,}")
    print(f"  Avg Order     : ${report.avg_order_value:,}")
    print(f"  Anomalies     : {len(report.anomalies)}")
    print(f"  Runtime       : {elapsed:.2f}s  ({rows_per_sec:,} rows/s)")
    print()
    print(f"  Output files:")
    print(f"    {summary_path}")
    print(f"    {md_path}")
    print(f"    {html_path}")
    if quarantined:
        print(f"    {quarantine_path}")
    print("=" * 60)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m reporter",
        description="Turn messy order CSVs into a clean monthly business report.",
    )
    parser.add_argument(
        "pattern",
        nargs="?",
        default=None,
        help='Glob pattern for CSV files, e.g. "exports/*.csv"',
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for output files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help=f"Run against sample_data/ with no configuration required",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.demo:
        print("Running demo against sample_data/ ...")
        run(DEMO_PATTERN, output_dir=args.output_dir, verbose=args.verbose)
    elif args.pattern:
        run(args.pattern, output_dir=args.output_dir, verbose=args.verbose)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
