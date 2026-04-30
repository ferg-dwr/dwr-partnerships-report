"""
generate_report.py — Orchestrates the full report generation pipeline.

Called by GitHub Actions after a new CSV is uploaded.
Loads data, runs all charts, injects the diff summary, and writes:
  - reports/index.html         — main report page
  - reports/network_tripartite.html
  - reports/network_bipartite.html
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from dwr_report.charts.networks import network_bipartite, network_tripartite
from dwr_report.charts.treemaps import treemap, treemap_coverage
from dwr_report.ingest.loader import PartnershipData
from dwr_report.ingest.taxonomy import enrich_science_fields

# Path to taxonomy CSV relative to repo root — used by coverage treemap
# and science field enrichment
TAXONOMY_PATH = Path("data/dwr_custom_taxonomy.csv")

# Jinja2 template paths relative to repo root
TRIPARTITE_TEMPLATE = Path("templates/network_tripartite.html")
BIPARTITE_TEMPLATE = Path("templates/network_bipartite.html")


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

    # --- Warnings ---
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
          <strong>i Removed IDs (verify intentional)</strong>
          <ul>{items}</ul>
        </div>"""

    # --- Changed partnership cards (collapsed by default, shown at bottom) ---
    changes_html = ""
    if diff.get("changed_rows"):
        cards = ""
        for row in diff["changed_rows"]:
            n_fields = len(row["changes"])
            # Extract org name for the card header if available
            org_change = next(
                (c for c in row["changes"] if c["field"] == "Partnership Organization Name"),
                None,
            )
            org_label = org_change["old"] if org_change else f"ID {row['id']}"

            field_rows = "".join(
                f"""<tr>
                  <td class="change-field">{c["field"]}</td>
                  <td class="change-old">{c["old"]}</td>
                  <td class="change-arrow">→</td>
                  <td class="change-new">{c["new"]}</td>
                </tr>"""
                for c in row["changes"]
            )
            cards += f"""
            <details class="change-card">
              <summary>
                <span class="change-id">ID {row["id"]}</span>
                <span class="change-org">{org_label}</span>
                <span class="change-count">{n_fields} field{"s" if n_fields != 1 else ""} changed</span>
              </summary>
              <table class="change-table">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Before</th>
                    <th></th>
                    <th>After</th>
                  </tr>
                </thead>
                <tbody>{field_rows}</tbody>
              </table>
            </details>"""

        changes_html = f"""
        <div class="changes-section">
          <h3>Updated partnerships</h3>
          {cards}
        </div>"""

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


def _build_plotly_charts(data: PartnershipData, taxonomy_path: Path) -> dict[str, str]:
    """
    Generate all Plotly charts and return them as inline HTML strings.
    Returns a dict keyed by chart name.
    """
    charts: dict[str, str] = {}

    # TODO: Accept diff_result parameter and annotate charts with change data:
    # - Treemap: outline newly added partnership science fields, flag removed ones
    # - Pass new_ids/removed_ids to distinguish new vs existing partnerships
    # Science fields treemap
    fig = treemap(
        data,
        path=["Science and Technology Fields"],
        title="Partnerships by Science & Technology Field",
    )
    charts["treemap_fields"] = fig.to_html(full_html=False, include_plotlyjs="cdn")

    # Coverage gap treemap (requires taxonomy + enrichment)
    if taxonomy_path.exists():
        enrich_science_fields(data, taxonomy_path)
        fig = treemap_coverage(data, taxonomy_path)
        charts["treemap_coverage"] = fig.to_html(full_html=False, include_plotlyjs=False)
    else:
        print(
            f"  Warning: taxonomy file not found at '{taxonomy_path}' — skipping coverage treemap"
        )
        charts["treemap_coverage"] = (
            "<p class='chart-missing'>Coverage treemap unavailable "
            f"(taxonomy file not found: {taxonomy_path})</p>"
        )

    return charts


def _build_network_charts(
    data: PartnershipData,
    output_dir: Path,
    tripartite_template: Path,
    bipartite_template: Path,
) -> dict[str, str]:
    """
    Generate network graphs, save them as standalone HTML files,
    and return iframe embed strings keyed by chart name.
    """
    iframes: dict[str, str] = {}

    # TODO: Accept diff_result parameter and annotate network graphs:
    # - New nodes (from new_ids): render with green glow or star marker
    # - Removed nodes (from removed_ids): render faded/dotted
    # - Changed edges: highlight in yellow
    # Tripartite: Science Field <-> Staff <-> Division
    # Note: enrich_science_fields() must have been called before this
    if "1st Level Science Category" in data.df.columns:
        try:
            html = network_tripartite(data, template_path=tripartite_template)
            out = output_dir / "network_tripartite.html"
            out.write_text(html, encoding="utf-8")
            iframes["network_tripartite"] = (
                '<iframe src="network_tripartite.html" '
                'width="100%" height="800px" frameborder="0" '
                'sandbox="allow-scripts allow-same-origin"></iframe>'
            )
        except Exception as e:
            print(f"  Warning: tripartite network failed — {e}")
            iframes["network_tripartite"] = f"<p class='chart-missing'>Chart unavailable: {e}</p>"
    else:
        iframes["network_tripartite"] = (
            "<p class='chart-missing'>Tripartite network unavailable "
            "(taxonomy enrichment was skipped)</p>"
        )

    # Bipartite: Division <-> Partner Organization
    try:
        html = network_bipartite(data, template_path=bipartite_template)
        out = output_dir / "network_bipartite.html"
        out.write_text(html, encoding="utf-8")
        iframes["network_bipartite"] = (
            '<iframe src="network_bipartite.html" '
            'width="100%" height="800px" frameborder="0" '
            'sandbox="allow-scripts allow-same-origin"></iframe>'
        )
    except Exception as e:
        print(f"  Warning: bipartite network failed — {e}")
        iframes["network_bipartite"] = f"<p class='chart-missing'>Chart unavailable: {e}</p>"

    return iframes


def _assemble_html(
    diff_banner: str,
    charts: dict[str, str],
    iframes: dict[str, str],
    generated_at: str,
) -> str:
    return f"""<!DOCTYPE html>
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

    nav {{
      display: flex;
      gap: 1rem;
      margin-bottom: 2rem;
      flex-wrap: wrap;
    }}
    nav a {{
      padding: 0.4rem 1rem;
      background: var(--blue-light);
      color: var(--blue-dark);
      border-radius: 4px;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.875rem;
    }}
    nav a:hover {{ background: var(--blue-mid); color: white; }}

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

    .changes-section {{ margin-top: 1rem; }}
    .changes-section h3 {{ font-size: 0.95rem; color: var(--blue-dark); margin: 0 0 0.5rem; }}

    .change-card {{ margin: 0.4rem 0; border: 1px solid var(--grey); border-radius: 6px; overflow: hidden; }}
    .change-card summary {{
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.6rem 0.9rem;
      background: white;
      user-select: none;
      list-style: none;
    }}
    .change-card summary::-webkit-details-marker {{ display: none; }}
    .change-card summary::before {{ content: "▶"; font-size: 0.65rem; color: #999; transition: transform 0.15s; }}
    .change-card[open] summary::before {{ transform: rotate(90deg); }}
    .change-id {{ font-weight: 700; color: var(--blue-dark); font-size: 0.8rem; white-space: nowrap; }}
    .change-org {{ flex: 1; font-size: 0.875rem; color: #333; }}
    .change-count {{ font-size: 0.78rem; color: #888; white-space: nowrap; }}

    .change-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
    .change-table th {{
      text-align: left;
      padding: 0.35rem 0.9rem;
      background: var(--blue-light);
      color: var(--blue-dark);
      font-weight: 600;
      font-size: 0.78rem;
    }}
    .change-table td {{ padding: 0.35rem 0.9rem; border-top: 1px solid var(--grey); vertical-align: top; }}
    .change-field {{ font-weight: 600; color: #444; width: 30%; }}
    .change-old {{ color: #c62828; width: 30%; word-break: break-word; }}
    .change-arrow {{ color: #999; width: 5%; text-align: center; }}
    .change-new {{ color: #2e7d32; width: 30%; word-break: break-word; }}
    .change-table tr:hover td {{ background: #fafafa; }}

    .chart-section {{ margin-bottom: 3rem; }}
    .chart-section h2 {{ color: var(--blue-dark); border-bottom: 1px solid var(--grey); padding-bottom: 0.5rem; margin-bottom: 1rem; }}
    .chart-missing {{ color: #888; font-style: italic; padding: 1rem; background: var(--grey); border-radius: 4px; }}

    iframe {{ border-radius: 6px; display: block; }}
  </style>
</head>
<body>
  <header>
    <h1>DWR Partnerships Report</h1>
    <p class="generated-at">Generated {generated_at}</p>
  </header>

  <nav>
    <a href="#treemap-fields">Science Fields</a>
    <a href="#treemap-coverage">Coverage Gaps</a>
    <a href="#network-tripartite">Field ↔ Staff ↔ Division</a>
    <a href="#network-bipartite">Division ↔ Partners</a>
  </nav>

  {diff_banner}

  <div class="chart-section" id="treemap-fields">
    <h2>Partnerships by Science &amp; Technology Field</h2>
    {charts["treemap_fields"]}
  </div>

  <div class="chart-section" id="treemap-coverage">
    <h2>Science Field Coverage (Grey = Gap)</h2>
    {charts["treemap_coverage"]}
  </div>

  <div class="chart-section" id="network-tripartite">
    <h2>Science Field ↔ Staff ↔ Division Network</h2>
    {iframes["network_tripartite"]}
  </div>

  <div class="chart-section" id="network-bipartite">
    <h2>Division ↔ Partner Organization Network</h2>
    {iframes["network_bipartite"]}
  </div>

</body>
</html>"""


def generate(
    csv_path: Path,
    diff_path: Path,
    output_path: Path,
    taxonomy_path: Path = TAXONOMY_PATH,
    tripartite_template: Path = TRIPARTITE_TEMPLATE,
    bipartite_template: Path = BIPARTITE_TEMPLATE,
) -> None:
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    data = PartnershipData(csv_path)

    print("Generating Plotly charts...")
    charts = _build_plotly_charts(data, taxonomy_path)

    print("Generating network charts...")
    iframes = _build_network_charts(data, output_dir, tripartite_template, bipartite_template)

    print("Assembling report...")
    diff_banner = _diff_banner(diff_path)
    generated_at = datetime.now(UTC).strftime("%B %d, %Y at %H:%M UTC")
    html = _assemble_html(diff_banner, charts, iframes, generated_at)

    output_path.write_text(html, encoding="utf-8")
    print(f"Report written to '{output_path}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--diff", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY_PATH)
    parser.add_argument("--tripartite-template", type=Path, default=TRIPARTITE_TEMPLATE)
    parser.add_argument("--bipartite-template", type=Path, default=BIPARTITE_TEMPLATE)
    args = parser.parse_args()

    generate(
        csv_path=args.csv,
        diff_path=args.diff,
        output_path=args.output,
        taxonomy_path=args.taxonomy,
        tripartite_template=args.tripartite_template,
        bipartite_template=args.bipartite_template,
    )
