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

from jinja2 import Environment, FileSystemLoader

from dwr_report.charts.networks import network_bipartite, network_tripartite
from dwr_report.charts.treemaps import treemap_coverage
from dwr_report.ingest.loader import PartnershipData
from dwr_report.ingest.taxonomy import enrich_science_fields

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path to taxonomy CSV relative to repo root — used by coverage treemap
# and science field enrichment
TAXONOMY_PATH = Path("data/dwr_custom_taxonomy.csv")

# Jinja2 template paths relative to repo root
REPORT_TEMPLATE = Path("templates/report.html")
TRIPARTITE_TEMPLATE = Path("templates/network_tripartite.html")
BIPARTITE_TEMPLATE = Path("templates/network_bipartite.html")


# ---------------------------------------------------------------------------
# Diff summary → HTML
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Chart generation helpers
# ---------------------------------------------------------------------------


def _build_plotly_charts(data: PartnershipData, taxonomy_path: Path) -> dict[str, str]:
    """
    Generate all Plotly charts and return them as inline HTML strings.
    Returns a dict keyed by chart name.
    """
    charts: dict[str, str] = {}

    # Coverage gap treemap (requires taxonomy + enrichment)
    # TODO: Accept diff_result parameter to annotate newly added/removed fields
    if taxonomy_path.exists():
        enrich_science_fields(data, taxonomy_path)
        # treemap_coverage returns a self-contained HTML string (custom SVG, no Plotly)
        charts["treemap_coverage"] = treemap_coverage(data, taxonomy_path)
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
                'width="100%" height="800px" frameborder="0"></iframe>'
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
            'width="100%" height="800px" frameborder="0"></iframe>'
        )
    except Exception as e:
        print(f"  Warning: bipartite network failed — {e}")
        iframes["network_bipartite"] = f"<p class='chart-missing'>Chart unavailable: {e}</p>"

    return iframes


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------


def _assemble_html(
    diff_banner: str,
    charts: dict[str, str],
    iframes: dict[str, str],
    generated_at: str,
    template_path: Path = REPORT_TEMPLATE,
) -> str:
    """Render the report HTML from a Jinja2 template."""
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,  # HTML content is pre-rendered and trusted
    )
    template = env.get_template(template_path.name)
    return template.render(
        generated_at=generated_at,
        diff_banner=diff_banner,
        iframe_treemap=iframes.get("treemap_coverage", ""),
        iframe_tripartite=iframes.get("network_tripartite", ""),
        iframe_bipartite=iframes.get("network_bipartite", ""),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate(
    csv_path: Path,
    diff_path: Path,
    output_path: Path,
    taxonomy_path: Path = TAXONOMY_PATH,
    report_template: Path = REPORT_TEMPLATE,
    tripartite_template: Path = TRIPARTITE_TEMPLATE,
    bipartite_template: Path = BIPARTITE_TEMPLATE,
) -> None:
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    data = PartnershipData(csv_path)

    print("Generating charts...")
    charts = _build_plotly_charts(data, taxonomy_path)

    # Save treemap as standalone HTML (React/Babel — needs its own document)
    treemap_path = output_dir / "treemap_coverage.html"
    treemap_path.write_text(charts.get("treemap_coverage", ""), encoding="utf-8")

    print("Generating network charts...")
    iframes = _build_network_charts(data, output_dir, tripartite_template, bipartite_template)
    iframes["treemap_coverage"] = (
        "<iframe src='treemap_coverage.html' id='treemap-iframe' width='100%' "
        "frameborder='0' scrolling='no' "
        "style='border:none;outline:none;display:block;'></iframe>"
    )

    print("Assembling report...")
    diff_banner = _diff_banner(diff_path)
    generated_at = datetime.now(UTC).strftime("%B %d, %Y at %H:%M UTC")
    html = _assemble_html(diff_banner, charts, iframes, generated_at, report_template)

    output_path.write_text(html, encoding="utf-8")
    print(f"Report written to '{output_path}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--diff", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY_PATH)
    parser.add_argument("--report-template", type=Path, default=REPORT_TEMPLATE)
    parser.add_argument("--tripartite-template", type=Path, default=TRIPARTITE_TEMPLATE)
    parser.add_argument("--bipartite-template", type=Path, default=BIPARTITE_TEMPLATE)
    args = parser.parse_args()

    generate(
        csv_path=args.csv,
        diff_path=args.diff,
        output_path=args.output,
        taxonomy_path=args.taxonomy,
        report_template=args.report_template,
        tripartite_template=args.tripartite_template,
        bipartite_template=args.bipartite_template,
    )
