"""
render_html.py — Professional single-file HTML report renderer.

Business problem: a finance-grade HTML report is the visual proof of quality
that convinces a prospective client this tool is production-ready. All CSS is
inlined (no CDN, no external requests) so the file can be emailed or opened
offline. The design follows finance-tool conventions: restrained palette,
tabular data, clear hierarchy — not a marketing template.
"""

import logging
from datetime import datetime
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Optional

from reporter.analyze import ReportData

logger = logging.getLogger(__name__)

_CSS = """
/* ── Reset & base ─────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                 'Helvetica Neue', Arial, sans-serif;
    font-size: 0.9rem;
    line-height: 1.55;
    background: #f5f5f5;
    color: #1a1a2e;
}

/* ── Layout ────────────────────────────────────────────────── */
.page {
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem 1.5rem 4rem;
}

/* ── Header ────────────────────────────────────────────────── */
header {
    border-bottom: 3px solid #1a1a2e;
    padding-bottom: 1rem;
    margin-bottom: 2rem;
}
header h1 {
    font-size: 1.7rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #1a1a2e;
}
header .meta {
    font-size: 0.78rem;
    color: #666;
    margin-top: 0.25rem;
}

/* ── KPI strip ─────────────────────────────────────────────── */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    margin-bottom: 2.5rem;
}
.kpi-card {
    background: #fff;
    border: 1px solid #e2e2e2;
    border-radius: 6px;
    padding: 1.1rem 1.2rem;
}
.kpi-card .label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #888;
    margin-bottom: 0.3rem;
}
.kpi-card .value {
    font-size: 1.45rem;
    font-weight: 700;
    color: #1a1a2e;
    letter-spacing: -0.02em;
}
.kpi-card.highlight .value { color: #0055cc; }
.kpi-card .sub {
    font-size: 0.72rem;
    color: #999;
    margin-top: 0.2rem;
}

/* ── Section ───────────────────────────────────────────────── */
section { margin-bottom: 2.5rem; }
section h2 {
    font-size: 1rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #555;
    border-bottom: 1px solid #ddd;
    padding-bottom: 0.4rem;
    margin-bottom: 1rem;
}

/* ── Tables ────────────────────────────────────────────────── */
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
    background: #fff;
    border: 1px solid #e2e2e2;
    border-radius: 6px;
    overflow: hidden;
}
thead th {
    background: #1a1a2e;
    color: #fff;
    font-weight: 600;
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.65rem 0.9rem;
    text-align: left;
}
thead th.num { text-align: right; }
tbody tr:nth-child(even) { background: #fafafa; }
tbody tr:hover { background: #f0f5ff; }
tbody td {
    padding: 0.55rem 0.9rem;
    border-top: 1px solid #eee;
    vertical-align: middle;
}
tbody td.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-family: 'SF Mono', 'Consolas', 'Courier New', monospace;
    font-size: 0.82rem;
}
.positive { color: #1a7a1a; font-weight: 600; }
.negative { color: #b52828; font-weight: 600; }
.rank-badge {
    display: inline-block;
    width: 24px; height: 24px;
    line-height: 24px;
    text-align: center;
    background: #e8eeff;
    color: #0055cc;
    border-radius: 50%;
    font-weight: 700;
    font-size: 0.75rem;
}

/* ── Anomaly cards ──────────────────────────────────────────── */
.anomaly-list { display: flex; flex-direction: column; gap: 0.7rem; }
.anomaly-card {
    background: #fff;
    border: 1px solid #e2e2e2;
    border-left: 4px solid #e67e00;
    border-radius: 4px;
    padding: 0.8rem 1rem;
}
.anomaly-card.high_value_order { border-left-color: #0055cc; }
.anomaly-tag {
    display: inline-block;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-weight: 700;
    padding: 0.1rem 0.5rem;
    border-radius: 3px;
    background: #fff3e0;
    color: #b35a00;
    margin-bottom: 0.3rem;
}
.anomaly-card.high_value_order .anomaly-tag {
    background: #e8eeff;
    color: #0055cc;
}
.anomaly-desc { font-weight: 500; font-size: 0.85rem; }
.anomaly-detail { font-size: 0.78rem; color: #888; margin-top: 0.2rem; }

/* ── Quality bar ────────────────────────────────────────────── */
.quality-row {
    display: flex;
    align-items: center;
    gap: 1.2rem;
    background: #fff;
    border: 1px solid #e2e2e2;
    border-radius: 6px;
    padding: 1rem 1.2rem;
}
.quality-bar-wrap { flex: 1; background: #eee; border-radius: 99px; height: 8px; }
.quality-bar { height: 8px; border-radius: 99px; background: #1a7a1a; }
.quality-label { font-size: 0.8rem; color: #555; white-space: nowrap; }

/* ── Footer ────────────────────────────────────────────────── */
footer {
    font-size: 0.72rem;
    color: #aaa;
    text-align: center;
    margin-top: 3rem;
    border-top: 1px solid #ddd;
    padding-top: 1rem;
}
"""


def _fmt_money(v: Decimal) -> str:
    return f"${v:,.2f}"


def _fmt_pct(v: Optional[Decimal]) -> str:
    if v is None:
        return '<span style="color:#bbb">—</span>'
    sign = "+" if v > 0 else ""
    cls = "positive" if v > 0 else "negative"
    return f'<span class="{cls}">{sign}{v:.1f}%</span>'


def _e(s: object) -> str:
    return escape(str(s))


def render_html(report: ReportData, path: str) -> None:
    """Writes a single-file HTML report with inline CSS to *path*."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    quality_pct = (report.valid_rows / report.total_raw_rows * 100) if report.total_raw_rows else 0

    # ------------------------------------------------------------------ #
    # KPI strip
    # ------------------------------------------------------------------ #
    kpi_strip = f"""
<div class="kpi-strip">
  <div class="kpi-card highlight">
    <div class="label">Net Revenue</div>
    <div class="value">{_e(_fmt_money(report.net_revenue))}</div>
    <div class="sub">{report.date_range_start} → {report.date_range_end}</div>
  </div>
  <div class="kpi-card">
    <div class="label">Total Orders</div>
    <div class="value">{report.total_orders:,}</div>
    <div class="sub">{report.months_covered} months</div>
  </div>
  <div class="kpi-card">
    <div class="label">Avg Order Value</div>
    <div class="value">{_e(_fmt_money(report.avg_order_value))}</div>
    <div class="sub">per transaction</div>
  </div>
  <div class="kpi-card">
    <div class="label">Refunds</div>
    <div class="value">{report.total_refunds:,}</div>
    <div class="sub">{_e(_fmt_money(report.total_refund_amount))} returned</div>
  </div>
  <div class="kpi-card">
    <div class="label">Data Quality</div>
    <div class="value">{quality_pct:.0f}%</div>
    <div class="sub">{report.quarantined_rows:,} rows quarantined</div>
  </div>
</div>
"""

    # ------------------------------------------------------------------ #
    # Monthly table
    # ------------------------------------------------------------------ #
    monthly_rows = ""
    for m in report.monthly:
        monthly_rows += f"""
  <tr>
    <td>{_e(m.year_month)}</td>
    <td class="num">{_e(_fmt_money(m.net_revenue))}</td>
    <td class="num">{m.order_count:,}</td>
    <td class="num">{m.refund_count} ({_e(_fmt_money(m.refund_amount))})</td>
    <td class="num">{_e(_fmt_money(m.avg_order_value))}</td>
    <td class="num">{_fmt_pct(m.mom_growth_pct)}</td>
  </tr>"""

    monthly_table = f"""
<table>
  <thead>
    <tr>
      <th>Month</th>
      <th class="num">Net Revenue</th>
      <th class="num">Orders</th>
      <th class="num">Refunds</th>
      <th class="num">Avg Order</th>
      <th class="num">MoM Growth</th>
    </tr>
  </thead>
  <tbody>{monthly_rows}
  </tbody>
</table>
"""

    # ------------------------------------------------------------------ #
    # Top 10 products table
    # ------------------------------------------------------------------ #
    top_rows = ""
    for i, p in enumerate(report.top_products, 1):
        top_rows += f"""
  <tr>
    <td><span class="rank-badge">{i}</span></td>
    <td>{_e(p.product_name)}</td>
    <td class="num">{_e(_fmt_money(p.total_revenue))}</td>
    <td class="num">{p.total_units:,}</td>
    <td class="num">{p.order_count:,}</td>
  </tr>"""

    top_table = f"""
<table>
  <thead>
    <tr>
      <th style="width:44px">#</th>
      <th>Product</th>
      <th class="num">Revenue</th>
      <th class="num">Units</th>
      <th class="num">Orders</th>
    </tr>
  </thead>
  <tbody>{top_rows}
  </tbody>
</table>
"""

    # ------------------------------------------------------------------ #
    # All products table
    # ------------------------------------------------------------------ #
    all_prod_rows = ""
    for p in report.products:
        all_prod_rows += f"""
  <tr>
    <td>{_e(p.product_name)}</td>
    <td class="num">{_e(_fmt_money(p.total_revenue))}</td>
    <td class="num">{p.total_units:,}</td>
    <td class="num">{p.order_count:,}</td>
  </tr>"""

    all_prod_table = f"""
<table>
  <thead>
    <tr>
      <th>Product</th>
      <th class="num">Revenue</th>
      <th class="num">Units</th>
      <th class="num">Orders</th>
    </tr>
  </thead>
  <tbody>{all_prod_rows}
  </tbody>
</table>
"""

    # ------------------------------------------------------------------ #
    # Anomalies
    # ------------------------------------------------------------------ #
    if report.anomalies:
        anomaly_items = ""
        for a in report.anomalies:
            anomaly_items += f"""
  <div class="anomaly-card {_e(a.kind)}">
    <div class="anomaly-tag">{_e(a.kind.replace('_', ' '))}</div>
    <div class="anomaly-desc">{_e(a.description)}</div>
    <div class="anomaly-detail">{_e(a.detail)}</div>
  </div>"""
        anomaly_section = f'<div class="anomaly-list">{anomaly_items}\n</div>'
    else:
        anomaly_section = '<p style="color:#888;font-size:0.85rem">No anomalies detected.</p>'

    # ------------------------------------------------------------------ #
    # Quality bar
    # ------------------------------------------------------------------ #
    quality_section = f"""
<div class="quality-row">
  <span class="quality-label">{report.valid_rows:,} valid / {report.total_raw_rows:,} total rows</span>
  <div class="quality-bar-wrap">
    <div class="quality-bar" style="width:{quality_pct:.1f}%"></div>
  </div>
  <span class="quality-label">{quality_pct:.1f}% clean · {report.quarantined_rows:,} quarantined</span>
</div>
"""

    # ------------------------------------------------------------------ #
    # Full HTML
    # ------------------------------------------------------------------ #
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sales Report — {report.date_range_start} to {report.date_range_end}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="page">

  <header>
    <h1>Sales Report</h1>
    <div class="meta">
      Period: {_e(report.date_range_start)} → {_e(report.date_range_end)} &nbsp;·&nbsp;
      Generated: {_e(generated_at)} &nbsp;·&nbsp;
      {report.total_raw_rows:,} source rows
    </div>
  </header>

  {kpi_strip}

  <section>
    <h2>Revenue by Month</h2>
    {monthly_table}
  </section>

  <section>
    <h2>Top 10 Products</h2>
    {top_table}
  </section>

  <section>
    <h2>All Products</h2>
    {all_prod_table}
  </section>

  <section>
    <h2>Attention — Anomalies</h2>
    {anomaly_section}
  </section>

  <section>
    <h2>Data Quality</h2>
    {quality_section}
  </section>

  <footer>
    Sales Report Automator &nbsp;·&nbsp; Standard library only (Python 3.11) &nbsp;·&nbsp; {_e(generated_at)}
  </footer>

</div>
</body>
</html>
"""

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)

    logger.info("HTML report written: %s", path)
