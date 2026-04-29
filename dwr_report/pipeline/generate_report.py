"""
generate_report.py — Orchestrates the full report generation pipeline.

Called by GitHub Actions after a new CSV is uploaded.
Loads data, runs charts, injects the diff summary, and writes reports/index.html.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from dwr_report.charts.treemaps import treemap
from dwr_report.ingest.loader import PartnershipData


def _diff_banner(diff_path: Path) -> str:
    """Render the diff result as an HTML summary banner."""
    if not diff_path.exists():
        return ""

    diff = json.loads(diff_path.read_text())

    new_count = len(diff.get("new_ids", []))
    removed_count = len(diff.get("removed_ids", []))
    changed_count = len(diff.get("changed_rows", []))
    warnings = diff.get("warnings", [])

    collision_warnings = [w for w in warnings if w["kind"] == "collision"]
    orphan_warnings = [w for w in warnings if w["kind"] == "orphan"]

    # Build warning HTML
    warning_html = ""
    if collision_warnings:
        items = "".join(f"<li>ID {w['id']}: {w['message']}</li>" for w in collision_warnings)
        warning_html += f"""
        <div class="banner banner--error">
          <strong>⚠️ ID Collision Warnings</strong>
          <ul>{items}</ul>
        </div>"""

    if orphan_warnings:
        items = "".join(f"<li>ID {w['id']}: {w['message']}</li>" for w in orphan_warnings)
        warning_html += f"""
        <div class="banner banner--warn">
          <strong>i️ Removed IDs (verify intentional)</strong>
          <ul>{items}</ul>
        </div>"""

    # Build changes detail
    changes_html = ""
    if diff.get("changed_rows"):
        rows = ""
        for row in diff["changed_rows"]:
            field_rows = "".join(
                f"<tr><td>{c['field']}</td><td>{c['old']}</td><td>{c['new']}</td></tr>"
                for c in row["changes"]
            )
            rows += f"""
            <details>
              <summary>ID {row["id"]}</summary>
              <table>
                <thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead>
                <tbody>{field_rows}</tbody>
              </table>
            </details>"""
        changes_html = f"<div class='changes'>{rows}</div>"

    return f"""
    <div class="diff-summary">
      <h2>What changed in this upload</h2>
      <div class="diff-stats">
        <span class="stat stat--new">+{new_count} new</span>
        <span class="stat stat--removed">-{removed_count} removed</span>
        <span class="stat stat--changed">~ {changed_count} updated</span>
      </div>
      {warning_html}
      {changes_html}
    </div>"""


def generate(csv_path: Path, diff_path: Path, output_path: Path) -> None:
    data = PartnershipData(csv_path)

    treemap_fig = treemap(
        data,
        path=["Science and Technology Fields"],
        title="Partnerships by Science & Technology Field",
    )
    treemap_html = treemap_fig.to_html(full_html=False, include_plotlyjs="cdn")

    # Diff banner
    diff_banner = _diff_banner(diff_path)

    # Timestamp
    generated_at = datetime.now(UTC).strftime("%B %d, %Y at %H:%M UTC")

    # Assemble the full page
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DWR Partnerships Report</title>
  <style>
    :root {{
      --blue-dark:  #084594;
      --blue-mid:   #6BAED6;
      --blue-light: #DEEBF7;
      --grey:       #D9D9D9;
      --green:      #2e7d32;
      --red:        #c62828;
      --orange:     #e65100;
      --text:       #1a1a1a;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem;
      color: var(--text);
    }}

    header {{
      border-bottom: 3px solid var(--blue-dark);
      margin-bottom: 2rem;
      padding-bottom: 1rem;
    }}

    h1 {{ color: var(--blue-dark); margin: 0 0 0.25rem; }}
    .generated-at {{ color: #666; font-size: 0.875rem; }}

    .diff-summary {{
      background: var(--blue-light);
      border-left: 4px solid var(--blue-mid);
      border-radius: 4px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 2rem;
    }}

    .diff-summary h2 {{ margin: 0 0 0.75rem; font-size: 1.1rem; color: var(--blue-dark); }}

    .diff-stats {{ display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }}

    .stat {{
      padding: 0.3rem 0.75rem;
      border-radius: 20px;
      font-weight: 600;
      font-size: 0.9rem;
    }}
    .stat--new     {{ background: #c8e6c9; color: var(--green); }}
    .stat--removed {{ background: #ffcdd2; color: var(--red); }}
    .stat--changed {{ background: #fff3e0; color: var(--orange); }}

    .banner {{
      border-radius: 4px;
      padding: 0.75rem 1rem;
      margin: 0.75rem 0;
      font-size: 0.9rem;
    }}
    .banner--error {{ background: #ffcdd2; border-left: 4px solid var(--red); }}
    .banner--warn  {{ background: #fff9c4; border-left: 4px solid #f9a825; }}
    .banner ul     {{ margin: 0.5rem 0 0; padding-left: 1.25rem; }}

    .changes details {{ margin: 0.5rem 0; }}
    .changes summary {{ cursor: pointer; font-weight: 600; padding: 0.25rem 0; }}
    .changes table   {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.85rem; }}
    .changes th, .changes td {{
      text-align: left;
      padding: 0.4rem 0.75rem;
      border-bottom: 1px solid var(--grey);
    }}
    .changes th {{ background: var(--blue-light); font-weight: 600; }}

    .chart-section {{ margin-bottom: 3rem; }}
    .chart-section h2 {{ color: var(--blue-dark); }}
  </style>
</head>
<body>
  <header>
    <h1>DWR Partnerships Report</h1>
    <p class="generated-at">Generated {generated_at}</p>
  </header>

  {diff_banner}

  <div class="chart-section">
    <h2>Science &amp; Technology Fields</h2>
    {treemap_html}
  </div>

</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Report written to '{output_path}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--diff", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    generate(args.csv, args.diff, args.output)
