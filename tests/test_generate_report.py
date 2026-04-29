"""
tests/test_generate_report.py — Unit tests for dwr_report.pipeline.generate_report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dwr_report.ingest.loader import PartnershipData
from dwr_report.pipeline.generate_report import (
    _assemble_html,
    _build_network_charts,
    _build_plotly_charts,
    _diff_banner,
    generate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_ROW = {
    "ID": 1,
    "Partnership Organization Name": '["UC Davis"]',
    "Organization Type": '["University"]',
    "Relevant DWR Program(s) and/ or Project(s)": '["Delta Science"]',
    "Partnership Type": '["Research"]',
    "Status of Partnership": '["Active"]',
    "DWR Investments": '["Funding"]',
    "Science and Technology Fields": '["Hydrology"]',
    "DWR Division/ Office/ Branch": "Flood Operations",
    "Main DWR Point of Contact": "Smith, Jane@DWR",
}

TAXONOMY_ROWS = [
    {
        "1st Level (Science Category)": "Geological and Earth Sciences",
        "2nd level (Science Field)": "Hydrology",
        "Description": "",
    },
    {
        "1st Level (Science Category)": "Atmospheric Sciences",
        "2nd level (Science Field)": "Climatology",
        "Description": "",
    },
]


def write_csv(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    p = tmp_path / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def write_diff(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "diff.json"
    p.write_text(json.dumps(data))
    return p


def make_minimal_template(tmp_path: Path, name: str) -> Path:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(exist_ok=True)
    t = templates_dir / name
    t.write_text(
        "<html><body>"
        "<script src='{{ vis_js_cdn }}'></script>"
        "<div>{{ nodes_json }}</div>"
        "</body></html>"
    )
    return t


def make_data(tmp_path: Path, rows: list[dict] | None = None) -> PartnershipData:
    rows = rows or [BASE_ROW]
    p = write_csv(tmp_path, "data.csv", rows)
    return PartnershipData(p)


# ---------------------------------------------------------------------------
# _diff_banner
# ---------------------------------------------------------------------------


class TestDiffBanner:
    def test_returns_empty_when_file_missing(self, tmp_path):
        result = _diff_banner(tmp_path / "nonexistent.json")
        assert result == ""

    def test_shows_new_count(self, tmp_path):
        p = write_diff(
            tmp_path, {"new_ids": [1, 2, 3], "removed_ids": [], "changed_rows": [], "warnings": []}
        )
        result = _diff_banner(p)
        assert "+3 new" in result

    def test_shows_removed_count(self, tmp_path):
        p = write_diff(
            tmp_path, {"new_ids": [], "removed_ids": [5], "changed_rows": [], "warnings": []}
        )
        result = _diff_banner(p)
        assert "-1 removed" in result

    def test_shows_changed_count(self, tmp_path):
        p = write_diff(
            tmp_path,
            {
                "new_ids": [],
                "removed_ids": [],
                "warnings": [],
                "changed_rows": [
                    {
                        "id": 1,
                        "changes": [
                            {"field": "Status of Partnership", "old": "Active", "new": "Inactive"}
                        ],
                    }
                ],
            },
        )
        result = _diff_banner(p)
        assert "~ 1 updated" in result

    def test_shows_collision_warning(self, tmp_path):
        p = write_diff(
            tmp_path,
            {
                "new_ids": [],
                "removed_ids": [],
                "changed_rows": [],
                "warnings": [{"kind": "collision", "id": 1, "message": "Name changed"}],
            },
        )
        result = _diff_banner(p)
        assert "Collision" in result
        assert "banner--error" in result

    def test_shows_orphan_warning(self, tmp_path):
        p = write_diff(
            tmp_path,
            {
                "new_ids": [],
                "removed_ids": [],
                "changed_rows": [],
                "warnings": [{"kind": "orphan", "id": 2, "message": "ID missing"}],
            },
        )
        result = _diff_banner(p)
        assert "banner--warn" in result

    def test_shows_changed_row_details(self, tmp_path):
        p = write_diff(
            tmp_path,
            {
                "new_ids": [],
                "removed_ids": [],
                "warnings": [],
                "changed_rows": [
                    {
                        "id": 42,
                        "changes": [
                            {"field": "Status of Partnership", "old": "Active", "new": "Inactive"}
                        ],
                    }
                ],
            },
        )
        result = _diff_banner(p)
        assert "ID 42" in result
        assert "Status of Partnership" in result

    def test_zero_counts_shown(self, tmp_path):
        p = write_diff(
            tmp_path, {"new_ids": [], "removed_ids": [], "changed_rows": [], "warnings": []}
        )
        result = _diff_banner(p)
        assert "+0 new" in result
        assert "-0 removed" in result
        assert "~ 0 updated" in result

    def test_returns_html_string(self, tmp_path):
        p = write_diff(
            tmp_path, {"new_ids": [1], "removed_ids": [], "changed_rows": [], "warnings": []}
        )
        result = _diff_banner(p)
        assert isinstance(result, str)
        assert "diff-summary" in result


# ---------------------------------------------------------------------------
# _build_plotly_charts
# ---------------------------------------------------------------------------


class TestBuildPlotlyCharts:
    def test_returns_treemap_fields(self, tmp_path):
        data = make_data(tmp_path)
        charts = _build_plotly_charts(data, tmp_path / "nonexistent_taxonomy.csv")
        assert "treemap_fields" in charts
        assert len(charts["treemap_fields"]) > 0

    def test_treemap_fields_contains_plotly(self, tmp_path):
        data = make_data(tmp_path)
        charts = _build_plotly_charts(data, tmp_path / "nonexistent_taxonomy.csv")
        assert "plotly" in charts["treemap_fields"].lower()

    def test_coverage_treemap_missing_taxonomy(self, tmp_path):
        data = make_data(tmp_path)
        charts = _build_plotly_charts(data, tmp_path / "nonexistent.csv")
        assert "chart-missing" in charts["treemap_coverage"]

    def test_coverage_treemap_with_taxonomy(self, tmp_path):
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = make_data(tmp_path)
        charts = _build_plotly_charts(data, tax_p)
        assert "chart-missing" not in charts["treemap_coverage"]
        assert len(charts["treemap_coverage"]) > 100

    def test_enrichment_adds_category_column(self, tmp_path):
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = make_data(tmp_path)
        _build_plotly_charts(data, tax_p)
        assert "1st Level Science Category" in data.df.columns


# ---------------------------------------------------------------------------
# _build_network_charts
# ---------------------------------------------------------------------------


class TestBuildNetworkCharts:
    def test_bipartite_iframe_present_without_enrichment(self, tmp_path):
        data = make_data(tmp_path)
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")
        iframes = _build_network_charts(data, tmp_path, tri_t, bi_t)
        assert "iframe" in iframes["network_bipartite"]

    def test_tripartite_skipped_without_enrichment(self, tmp_path):
        data = make_data(tmp_path)
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")
        iframes = _build_network_charts(data, tmp_path, tri_t, bi_t)
        assert "chart-missing" in iframes["network_tripartite"]

    def test_tripartite_present_with_enrichment(self, tmp_path):
        from dwr_report.ingest.taxonomy import enrich_science_fields

        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = make_data(tmp_path)
        enrich_science_fields(data, tax_p)
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")
        iframes = _build_network_charts(data, tmp_path, tri_t, bi_t)
        assert "iframe" in iframes["network_tripartite"]

    def test_network_files_written_to_disk(self, tmp_path):
        from dwr_report.ingest.taxonomy import enrich_science_fields

        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = make_data(tmp_path)
        enrich_science_fields(data, tax_p)
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")
        _build_network_charts(data, tmp_path, tri_t, bi_t)
        assert (tmp_path / "network_bipartite.html").exists()
        assert (tmp_path / "network_tripartite.html").exists()

    def test_missing_template_produces_fallback(self, tmp_path):
        data = make_data(tmp_path)
        tri_t = tmp_path / "templates" / "network_tripartite.html"  # doesn't exist
        bi_t = tmp_path / "templates" / "network_bipartite.html"  # doesn't exist
        iframes = _build_network_charts(data, tmp_path, tri_t, bi_t)
        assert "chart-missing" in iframes["network_bipartite"]


# ---------------------------------------------------------------------------
# _assemble_html
# ---------------------------------------------------------------------------


class TestAssembleHtml:
    def make_inputs(self) -> tuple[str, dict, dict, str]:
        diff_banner = "<div class='diff-summary'>changes</div>"
        charts = {
            "treemap_fields": "<div>treemap fields</div>",
            "treemap_coverage": "<div>treemap coverage</div>",
        }
        iframes = {
            "network_tripartite": "<iframe src='network_tripartite.html'></iframe>",
            "network_bipartite": "<iframe src='network_bipartite.html'></iframe>",
        }
        generated_at = "April 29, 2026 at 12:00 UTC"
        return diff_banner, charts, iframes, generated_at

    def test_returns_valid_html(self):
        result = _assemble_html(*self.make_inputs())
        assert result.startswith("<!DOCTYPE html>")
        assert "</html>" in result

    def test_contains_diff_banner(self):
        result = _assemble_html(*self.make_inputs())
        assert "diff-summary" in result

    def test_contains_all_chart_sections(self):
        result = _assemble_html(*self.make_inputs())
        assert "treemap-fields" in result
        assert "treemap-coverage" in result
        assert "network-tripartite" in result
        assert "network-bipartite" in result

    def test_contains_nav_links(self):
        result = _assemble_html(*self.make_inputs())
        assert "<nav>" in result
        assert "Science Fields" in result

    def test_contains_timestamp(self):
        result = _assemble_html(*self.make_inputs())
        assert "April 29, 2026 at 12:00 UTC" in result

    def test_contains_chart_content(self):
        result = _assemble_html(*self.make_inputs())
        assert "treemap fields" in result
        assert "treemap coverage" in result


# ---------------------------------------------------------------------------
# generate() — integration
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_creates_index_html(self, tmp_path):
        csv_p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        diff_p = write_diff(
            tmp_path, {"new_ids": [], "removed_ids": [], "changed_rows": [], "warnings": []}
        )
        out_p = tmp_path / "reports" / "index.html"
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")

        generate(
            csv_p,
            diff_p,
            out_p,
            taxonomy_path=tax_p,
            tripartite_template=tri_t,
            bipartite_template=bi_t,
        )

        assert out_p.exists()

    def test_output_is_valid_html(self, tmp_path):
        csv_p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        diff_p = write_diff(
            tmp_path, {"new_ids": [], "removed_ids": [], "changed_rows": [], "warnings": []}
        )
        out_p = tmp_path / "reports" / "index.html"
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")

        generate(
            csv_p,
            diff_p,
            out_p,
            taxonomy_path=tax_p,
            tripartite_template=tri_t,
            bipartite_template=bi_t,
        )

        content = out_p.read_text()
        assert "<!DOCTYPE html>" in content
        assert "DWR Partnerships Report" in content

    def test_creates_parent_directories(self, tmp_path):
        csv_p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        diff_p = write_diff(
            tmp_path, {"new_ids": [], "removed_ids": [], "changed_rows": [], "warnings": []}
        )
        out_p = tmp_path / "deep" / "nested" / "reports" / "index.html"
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")

        generate(csv_p, diff_p, out_p, tripartite_template=tri_t, bipartite_template=bi_t)

        assert out_p.exists()

    def test_missing_diff_file_still_generates(self, tmp_path):
        csv_p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        diff_p = tmp_path / "nonexistent_diff.json"
        out_p = tmp_path / "reports" / "index.html"
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")

        generate(csv_p, diff_p, out_p, tripartite_template=tri_t, bipartite_template=bi_t)

        assert out_p.exists()

    def test_diff_banner_reflected_in_output(self, tmp_path):
        csv_p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        diff_p = write_diff(
            tmp_path, {"new_ids": [99, 100], "removed_ids": [], "changed_rows": [], "warnings": []}
        )
        out_p = tmp_path / "reports" / "index.html"
        tri_t = make_minimal_template(tmp_path, "network_tripartite.html")
        bi_t = make_minimal_template(tmp_path, "network_bipartite.html")

        generate(csv_p, diff_p, out_p, tripartite_template=tri_t, bipartite_template=bi_t)

        content = out_p.read_text()
        assert "+2 new" in content
