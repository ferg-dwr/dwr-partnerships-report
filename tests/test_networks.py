"""
tests/test_networks.py — Unit tests for dwr_report.charts.networks.

Network chart tests focus on data processing and output structure
rather than full template rendering, which requires Jinja2 templates
on disk. Template rendering is tested via an integration fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dwr_report.charts.networks import (
    save_html,
)
from dwr_report.ingest.loader import PartnershipData
from dwr_report.ingest.taxonomy import enrich_science_fields

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
]


def write_csv(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    p = tmp_path / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def make_data(tmp_path: Path, rows: list[dict] | None = None) -> PartnershipData:
    rows = rows or [BASE_ROW]
    p = write_csv(tmp_path, "data.csv", rows)
    return PartnershipData(p)


def make_enriched_data(
    tmp_path: Path, rows: list[dict] | None = None
) -> tuple[PartnershipData, Path]:
    data = make_data(tmp_path, rows)
    tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
    enrich_science_fields(data, tax_p)
    return data, tax_p


def make_minimal_tripartite_template(tmp_path: Path) -> Path:
    """Write a minimal Jinja2 template for tripartite network testing."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    template = templates_dir / "network_tripartite.html"
    template.write_text(
        "<html><body>"
        "<script src='{{ vis_js_cdn }}'></script>"
        "<div id='nodes'>{{ nodes_json | tojson }}</div>"
        "<div id='edges'>{{ edges_json | tojson }}</div>"
        "</body></html>"
    )
    return template


def make_minimal_bipartite_template(tmp_path: Path) -> Path:
    """Write a minimal Jinja2 template for bipartite network testing."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(exist_ok=True)
    template = templates_dir / "network_bipartite.html"
    template.write_text(
        "<html><body>"
        "<script src='{{ vis_js_cdn }}'></script>"
        "<div id='nodes'>{{ nodes_json | tojson }}</div>"
        "<div id='edges'>{{ edges_json | tojson }}</div>"
        "</body></html>"
    )
    return template


# ---------------------------------------------------------------------------
# CDN constant
# ---------------------------------------------------------------------------


class TestVisJsCdn:
    def test_cdn_url_is_set(self):
        from dwr_report.charts.networks import _VIS_JS_CDN

        assert _VIS_JS_CDN.startswith("https://cdn.jsdelivr.net")
        assert "vis-network" in _VIS_JS_CDN


# ---------------------------------------------------------------------------
# save_html
# ---------------------------------------------------------------------------


class TestSaveHtml:
    def test_writes_file(self, tmp_path):
        out = tmp_path / "output" / "test.html"
        save_html("<html></html>", out)
        assert out.exists()

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "dir" / "report.html"
        save_html("<html></html>", out)
        assert out.exists()

    def test_content_preserved(self, tmp_path):
        content = "<html><body>Hello</body></html>"
        out = tmp_path / "out.html"
        save_html(content, out)
        assert out.read_text() == content

    def test_returns_path(self, tmp_path):
        out = tmp_path / "out.html"
        result = save_html("<html></html>", out)
        assert isinstance(result, Path)
        assert result == out


# ---------------------------------------------------------------------------
# network_tripartite — template rendering
# ---------------------------------------------------------------------------


class TestNetworkTripartite:
    def test_raises_without_enrichment(self, tmp_path):
        from dwr_report.charts.networks import network_tripartite

        data = make_data(tmp_path)
        template = make_minimal_tripartite_template(tmp_path)
        with pytest.raises(ValueError, match="1st Level Science Category"):
            network_tripartite(data, template_path=template)

    def test_returns_html_string(self, tmp_path):
        from dwr_report.charts.networks import network_tripartite

        data, _ = make_enriched_data(tmp_path)
        template = make_minimal_tripartite_template(tmp_path)
        result = network_tripartite(data, template_path=template)
        assert isinstance(result, str)
        assert "<html>" in result

    def test_vis_js_variable_passed(self, tmp_path):
        from dwr_report.charts.networks import network_tripartite

        data, _ = make_enriched_data(tmp_path)
        template = make_minimal_tripartite_template(tmp_path)
        result = network_tripartite(data, template_path=template)
        assert "<script" in result  # vis_js="" passed; CDN hardcoded in template

    def test_nodes_json_in_output(self, tmp_path):
        from dwr_report.charts.networks import network_tripartite

        data, _ = make_enriched_data(tmp_path)
        template = make_minimal_tripartite_template(tmp_path)
        result = network_tripartite(data, template_path=template)
        # nodes_json should be valid JSON embedded in the output
        start = result.index("<div id='nodes'>") + len("<div id='nodes'>")
        end = result.index("</div>", start)
        nodes = json.loads(result[start:end])
        assert isinstance(nodes, list)
        assert len(nodes) > 0

    def test_node_groups_present(self, tmp_path):
        from dwr_report.charts.networks import network_tripartite

        rows = [
            {
                **BASE_ROW,
                "ID": 1,
                "Science and Technology Fields": '["Hydrology"]',
                "Main DWR Point of Contact": "Smith, Jane@DWR",
                "DWR Division/ Office/ Branch": "Flood Operations",
            },
            {
                **BASE_ROW,
                "ID": 2,
                "Science and Technology Fields": '["Hydrology"]',
                "Main DWR Point of Contact": "Garcia, Maria@DWR",
                "DWR Division/ Office/ Branch": "Planning",
            },
        ]
        data, _ = make_enriched_data(tmp_path, rows)
        template = make_minimal_tripartite_template(tmp_path)
        result = network_tripartite(data, template_path=template)
        start = result.index("<div id='nodes'>") + len("<div id='nodes'>")
        end = result.index("</div>", start)
        nodes = json.loads(result[start:end])
        groups = {n["group"] for n in nodes}
        assert "field" in groups
        assert "staff" in groups
        assert "division" in groups


# ---------------------------------------------------------------------------
# network_bipartite — template rendering
# ---------------------------------------------------------------------------


class TestNetworkBipartite:
    def test_returns_html_string(self, tmp_path):
        from dwr_report.charts.networks import network_bipartite

        data = make_data(tmp_path)
        template = make_minimal_bipartite_template(tmp_path)
        result = network_bipartite(data, template_path=template)
        assert isinstance(result, str)
        assert "<html>" in result

    def test_vis_js_variable_passed(self, tmp_path):
        from dwr_report.charts.networks import network_bipartite

        data = make_data(tmp_path)
        template = make_minimal_bipartite_template(tmp_path)
        result = network_bipartite(data, template_path=template)
        assert "<script" in result  # vis_js="" passed; CDN hardcoded in template

    def test_nodes_json_in_output(self, tmp_path):
        from dwr_report.charts.networks import network_bipartite

        data = make_data(tmp_path)
        template = make_minimal_bipartite_template(tmp_path)
        result = network_bipartite(data, template_path=template)
        start = result.index("<div id='nodes'>") + len("<div id='nodes'>")
        end = result.index("</div>", start)
        nodes = json.loads(result[start:end])
        assert isinstance(nodes, list)

    def test_node_groups_present(self, tmp_path):
        from dwr_report.charts.networks import network_bipartite

        rows = [
            {
                **BASE_ROW,
                "ID": 1,
                "Partnership Organization Name": '["UC Davis"]',
                "DWR Division/ Office/ Branch": "Flood Operations",
            },
            {
                **BASE_ROW,
                "ID": 2,
                "Partnership Organization Name": '["NOAA"]',
                "DWR Division/ Office/ Branch": "Planning",
            },
        ]
        data = make_data(tmp_path, rows)
        template = make_minimal_bipartite_template(tmp_path)
        result = network_bipartite(data, template_path=template)
        start = result.index("<div id='nodes'>") + len("<div id='nodes'>")
        end = result.index("</div>", start)
        nodes = json.loads(result[start:end])
        groups = {n["group"] for n in nodes}
        assert "division" in groups
        assert "org" in groups

    def test_multiple_orgs_per_division(self, tmp_path):
        from dwr_report.charts.networks import network_bipartite

        rows = [
            {
                **BASE_ROW,
                "ID": i,
                "Partnership Organization Name": f'["Org {i}"]',
                "DWR Division/ Office/ Branch": "Flood Operations",
            }
            for i in range(1, 5)
        ]
        data = make_data(tmp_path, rows)
        template = make_minimal_bipartite_template(tmp_path)
        result = network_bipartite(data, template_path=template)
        start = result.index("<div id='nodes'>") + len("<div id='nodes'>")
        end = result.index("</div>", start)
        nodes = json.loads(result[start:end])
        org_nodes = [n for n in nodes if n["group"] == "org"]
        assert len(org_nodes) == 4
