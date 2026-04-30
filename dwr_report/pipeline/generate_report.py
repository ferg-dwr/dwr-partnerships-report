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
        fig = treemap_coverage(data, taxonomy_path)
        charts["treemap_coverage"] = fig.to_html(full_html=False, include_plotlyjs="cdn")
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
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DWR Partnerships Report</title>
  <style>
    :root {{
      --blue-dark:  #003366;
      --blue-mid:   #0071BC;
      --blue-light: #E8F0F7;
      --gold:       #C8960C;
      --grey:       #D9D9D9;
      --grey-light: #F5F7FA;
      --green:      #2e7d32;
      --red:        #c62828;
      --orange:     #e65100;
      --text:       #333333;
      --border:     #CCCCCC;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;
      margin: 0; padding: 0;
      color: var(--text);
      background: #fff;
    }}

    /* ── Header ── */
    header {{
      background: var(--blue-dark);
      border-bottom: 5px solid var(--gold);
      padding: 1.25rem 2rem 1rem;
    }}

    .header-org {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: rgba(255,255,255,0.65);
      font-weight: 400;
      margin-bottom: 0.3rem;
    }}

    h1 {{
      color: white;
      margin: 0 0 0.5rem;
      font-size: 2rem;
      font-weight: 900;
      font-family: Arial Black, Arial, sans-serif;
      letter-spacing: -0.01em;
      line-height: 1.1;
    }}

    .header-meta {{
      display: flex;
      align-items: center;
      gap: 1.5rem;
      flex-wrap: wrap;
      margin-top: 0.25rem;
    }}

    .generated-at {{
      color: rgba(255,255,255,0.6);
      font-size: 0.78rem;
      flex: 1;
    }}

    /* ── Nav tabs in header ── */
    .header-nav {{
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
      margin-top: 0.75rem;
    }}

    .header-nav a {{
      padding: 0.3rem 0.8rem;
      background: rgba(255,255,255,0.12);
      color: rgba(255,255,255,0.85);
      border-radius: 3px;
      text-decoration: none;
      font-size: 0.78rem;
      font-weight: 600;
      border: 1px solid rgba(255,255,255,0.2);
      transition: all 0.15s;
      white-space: nowrap;
    }}
    .header-nav a:hover {{
      background: rgba(255,255,255,0.25);
      color: white;
      border-color: rgba(255,255,255,0.4);
    }}

    .btn-update {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.4rem 1rem;
      background: var(--gold);
      color: white;
      border-radius: 3px;
      text-decoration: none;
      font-size: 0.78rem;
      font-weight: 700;
      white-space: nowrap;
      transition: background 0.15s;
      flex-shrink: 0;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .btn-update:hover {{ background: #a67a08; }}

    /* ── Floating TOC ── */
    #floating-toc {{
      position: fixed;
      left: 1rem;
      top: 50%;
      transform: translateY(-50%);
      z-index: 900;
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
    }}

    .toc-item {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.75rem;
      background: rgba(255,255,255,0.95);
      border: 1px solid var(--border);
      border-radius: 4px;
      text-decoration: none;
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--blue-dark);
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      transition: all 0.15s;
      white-space: nowrap;
    }}
    .toc-item::before {{
      content: "";
      width: 6px; height: 6px;
      border-radius: 50%;
      background: var(--grey);
      flex-shrink: 0;
      transition: background 0.15s;
    }}
    .toc-item:hover, .toc-item.active {{
      background: var(--blue-dark);
      color: white;
      border-color: var(--blue-dark);
    }}
    .toc-item:hover::before, .toc-item.active::before {{
      background: var(--gold);
    }}

    /* ── Main content ── */
    .main-content {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 1.5rem 2rem 3rem 2rem;
    }}

    /* ── Diff summary ── */
    .diff-summary {{
      background: var(--blue-light);
      border-left: 4px solid var(--blue-mid);
      border-radius: 4px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 2rem;
    }}
    .diff-summary h2 {{ margin: 0 0 0.75rem; font-size: 1rem; color: var(--blue-dark); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }}
    .diff-stats {{ display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }}
    .stat {{
      padding: 0.3rem 0.75rem;
      border-radius: 20px;
      font-weight: 600;
      font-size: 0.875rem;
    }}
    .stat--new     {{ background: #c8e6c9; color: var(--green); }}
    .stat--removed {{ background: #ffcdd2; color: var(--red); }}
    .stat--changed {{ background: #fff3e0; color: var(--orange); }}

    .banner {{ border-radius: 4px; padding: 0.75rem 1rem; margin: 0.75rem 0; font-size: 0.875rem; }}
    .banner--error {{ background: #ffcdd2; border-left: 4px solid var(--red); }}
    .banner--warn  {{ background: #fff9c4; border-left: 4px solid #f9a825; }}
    .banner ul {{ margin: 0.5rem 0 0; padding-left: 1.25rem; }}

    .changes-section {{ margin-top: 1rem; }}
    .changes-section h3 {{ font-size: 0.85rem; color: var(--blue-dark); margin: 0 0 0.5rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    .change-card {{ margin: 0.4rem 0; border: 1px solid var(--grey); border-radius: 4px; overflow: hidden; }}
    .change-card summary {{ cursor: pointer; display: flex; align-items: center; gap: 0.75rem; padding: 0.6rem 0.9rem; background: white; user-select: none; list-style: none; }}
    .change-card summary::-webkit-details-marker {{ display: none; }}
    .change-card summary::before {{ content: "▶"; font-size: 0.65rem; color: #999; transition: transform 0.15s; }}
    .change-card[open] summary::before {{ transform: rotate(90deg); }}
    .change-id {{ font-weight: 700; color: var(--blue-dark); font-size: 0.8rem; white-space: nowrap; }}
    .change-org {{ flex: 1; font-size: 0.875rem; color: #333; }}
    .change-count {{ font-size: 0.78rem; color: #888; white-space: nowrap; }}
    .change-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
    .change-table th {{ text-align: left; padding: 0.35rem 0.9rem; background: var(--blue-light); color: var(--blue-dark); font-weight: 600; font-size: 0.78rem; }}
    .change-table td {{ padding: 0.35rem 0.9rem; border-top: 1px solid var(--grey); vertical-align: top; }}
    .change-field {{ font-weight: 600; color: #444; width: 30%; }}
    .change-old {{ color: #c62828; width: 30%; word-break: break-word; }}
    .change-arrow {{ color: #999; width: 5%; text-align: center; }}
    .change-new {{ color: #2e7d32; width: 30%; word-break: break-word; }}
    .change-table tr:hover td {{ background: #fafafa; }}

    /* ── Chart sections ── */
    .chart-section {{ margin-bottom: 3rem; scroll-margin-top: 1.5rem; }}
    .chart-section h2 {{
      color: var(--blue-dark);
      font-family: Arial Black, Arial, sans-serif;
      font-size: 1.25rem;
      font-weight: 900;
      border-bottom: 2px solid var(--gold);
      padding-bottom: 0.5rem;
      margin-bottom: 0.75rem;
      letter-spacing: -0.01em;
    }}
    .chart-context {{
      font-size: 0.85rem;
      color: #555;
      line-height: 1.6;
      margin-bottom: 1rem;
      padding: 0.75rem 1rem;
      background: var(--blue-light);
      border-left: 3px solid var(--blue-mid);
      border-radius: 0 4px 4px 0;
    }}
    .chart-missing {{ color: #888; font-style: italic; padding: 1rem; background: var(--grey); border-radius: 4px; }}
    iframe {{ border-radius: 4px; display: block; border: 1px solid var(--border); }}
  </style>
</head>
<body>
  <header>
    <div class="header-org">California Department of Water Resources &nbsp;·&nbsp; Science &amp; Technology Partnerships</div>
    <h1>DWR Partnerships Report</h1>
    <div class="header-meta">
      <span class="generated-at">Generated {generated_at}</span>
      <a href="upload-ui/" class="btn-update">⬆ Update Data</a>
    </div>
    <nav class="header-nav">
      <a href="#treemap-coverage">Coverage Gaps</a>
      <a href="#network-tripartite">Organizaitonal Network: Science, Staff, and Structure</a>
      <a href="#network-bipartite">DWR and Partner Organizations</a>
    </nav>
  </header>

  <!-- Floating TOC -->
  <nav id="floating-toc">
    <a href="#treemap-coverage"   class="toc-item">Coverage Gaps</a>
    <a href="#network-tripartite" class="toc-item">Science Network</a>
    <a href="#network-bipartite"  class="toc-item">Partner Network</a>
  </nav>

  <div class="main-content">

  {diff_banner}

  <div class="chart-section" id="treemap-coverage">
    <h2>Science Field Coverage</h2>
    <p class="chart-context">
      Darker blue indicates more partnerships in that science field. Grey fields have no current partnerships — these represent potential coverage gaps.
    </p>
    {charts["treemap_coverage"]}
  </div>

  <div class="chart-section" id="network-tripartite">
    <h2>Organizaitonal Network: Science, Staff, and Structure</h2>
    <p class="chart-context">
      Use this network to explore how DWR staff connect science and technology fields
      to divisions, offices, and branches. Each node represents a science field (left),
      a DWR point of contact (center), or a division/office/branch (right). An edge
      indicates that a staff member is the point of contact for a partnership in that
      science field. <strong>Click any node</strong> to highlight its connections.
      Note: this figure reflects only partnerships where a staff member is listed as
      the primary point of contact — it does not capture all staff engagement.
    </p>
    {iframes["network_tripartite"]}
  </div>

  <div class="chart-section" id="network-bipartite">
    <h2>Organizational Network: DWR and Partner Organizations</h2>
    <p class="chart-context">
      Use this network to explore how DWR divisions, offices, and branches connect
      to external partner organizations. Node size reflects the total number of
      partnerships — larger nodes are more connected. Edge width represents the
      number of partnerships between a division and an organization.
      <strong>Click any node</strong> to highlight its connections and see a summary.
    </p>
    {iframes["network_bipartite"]}
  </div>

  </div>

  <script>
    // ── Floating TOC active section tracking ──
    var tocItems = document.querySelectorAll('.toc-item');
    var sections = ['treemap-coverage', 'network-tripartite', 'network-bipartite']
      .map(function(id) {{ return document.getElementById(id); }})
      .filter(Boolean);

    function updateToc() {{
      var scrollY = window.scrollY + window.innerHeight * 0.3;
      var active = sections[0];
      sections.forEach(function(s) {{
        if (s.offsetTop <= scrollY) active = s;
      }});
      tocItems.forEach(function(a) {{
        var href = a.getAttribute('href').slice(1);
        a.classList.toggle('active', href === active.id);
      }});
    }}

    window.addEventListener('scroll', updateToc, {{ passive: true }});
    updateToc();
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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
