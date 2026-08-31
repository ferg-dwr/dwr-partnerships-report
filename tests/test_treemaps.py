"""
tests/test_treemaps.py — Unit tests for dwr_report.charts.treemaps.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dwr_report import content
from dwr_report.charts.treemaps import (
    treemap,
    treemap_coverage,
    treemap_coverage_svg,
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
    {
        "1st Level (Science Category)": "Atmospheric Sciences",
        "2nd level (Science Field)": "Climatology",
        "Description": "",
    },
    {
        "1st Level (Science Category)": "Atmospheric Sciences",
        "2nd level (Science Field)": "Meteorology",
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


# ---------------------------------------------------------------------------
# treemap()
# ---------------------------------------------------------------------------


class TestTreemap:
    def test_returns_figure(self, tmp_path):
        import plotly.graph_objects as go

        data = make_data(tmp_path)
        fig = treemap(data, path=["Science and Technology Fields"])
        assert isinstance(fig, go.Figure)

    def test_default_count_values(self, tmp_path):
        rows = [
            {**BASE_ROW, "ID": 1, "Science and Technology Fields": '["Hydrology"]'},
            {**BASE_ROW, "ID": 2, "Science and Technology Fields": '["Hydrology"]'},
            {**BASE_ROW, "ID": 3, "Science and Technology Fields": '["Climatology"]'},
        ]
        data = make_data(tmp_path, rows)
        fig = treemap(data, path=["Science and Technology Fields"])
        # Figure should have data
        assert len(fig.data) > 0

    def test_custom_title(self, tmp_path):
        data = make_data(tmp_path)
        fig = treemap(data, path=["Science and Technology Fields"], title="My Chart")
        assert fig.layout.title.text == "My Chart"

    def test_raises_on_missing_path_column(self, tmp_path):
        data = make_data(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            treemap(data, path=["Nonexistent Column"])

    def test_raises_on_missing_values_column(self, tmp_path):
        data = make_data(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            treemap(data, path=["Science and Technology Fields"], values="Nonexistent")

    def test_hierarchical_path(self, tmp_path):
        import plotly.graph_objects as go

        rows = [
            {
                **BASE_ROW,
                "ID": 1,
                "Organization Type": '["University"]',
                "Science and Technology Fields": '["Hydrology"]',
            },
            {
                **BASE_ROW,
                "ID": 2,
                "Organization Type": '["NGO"]',
                "Science and Technology Fields": '["Climatology"]',
            },
        ]
        data = make_data(tmp_path, rows)
        fig = treemap(data, path=["Organization Type", "Science and Technology Fields"])
        assert isinstance(fig, go.Figure)


# ---------------------------------------------------------------------------
# treemap_coverage()
# ---------------------------------------------------------------------------


class TestTreemapCoverage:
    def test_returns_html_string(self, tmp_path):
        data = make_data(tmp_path)
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        html = treemap_coverage(data, tax_p)
        assert isinstance(html, str)
        assert len(html) > 100

    def test_includes_zero_count_fields(self, tmp_path):
        """Fields with no partnerships should still appear in the taxonomy JSON."""
        data = make_data(tmp_path)  # Only has Hydrology
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        html = treemap_coverage(data, tax_p)
        # Climatology and Meteorology have 0 partnerships but appear in taxonomy
        assert "Climatology" in html or "Meteorology" in html

    def test_contains_taxonomy_json(self, tmp_path):
        data = make_data(tmp_path)
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        html = treemap_coverage(data, tax_p)
        assert "window.DWR_TAXONOMY" in html
        assert "subfields" in html


# ---------------------------------------------------------------------------
# Terminology guards
#
# Lindsay Correa's July 2026 review flagged that the treemap totals were labelled
# "PARTNERSHIPS" when they actually count science field tags. A partnership
# initiative tagged with four science fields contributes four field tags, so the
# two numbers are never interchangeable. These tests pin the vocabulary so the
# conflation cannot silently return — a label is exactly the kind of string
# someone edits in passing.
# ---------------------------------------------------------------------------


TWO_FIELD_ROW = {
    **BASE_ROW,
    "ID": 2,
    "Science and Technology Fields": '["Hydrology", "Climatology"]',
}


class TestTreemapTerminology:
    def test_grand_total_is_labelled_field_tags_not_partnerships(self, tmp_path):
        """Two initiatives carrying three field tags must not read as 3 partnerships."""
        data = make_data(tmp_path, [BASE_ROW, TWO_FIELD_ROW])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        svg, _ = treemap_coverage_svg(data, tax_p)

        # 1 tag on BASE_ROW + 2 tags on TWO_FIELD_ROW = 3 field tags, 2 initiatives.
        assert ">3<" in svg
        assert content.TERM_FIELD_TAGS.upper() in svg
        assert ">PARTNERSHIPS<" not in svg  # the original mislabel

    def test_science_areas_shows_a_denominator(self, tmp_path):
        """Lindsay asked '8 of 8?' — the stat needs parity with 'x/y SUBFIELDS'."""
        data = make_data(tmp_path, [BASE_ROW, TWO_FIELD_ROW])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        svg, _ = treemap_coverage_svg(data, tax_p)

        # Both taxonomy categories have a covered subfield; Meteorology is a gap.
        assert ">2/2<" in svg
        assert ">2/3<" in svg
        assert "SCIENCE AREAS COVERED" in svg

    def test_cell_tooltips_count_initiatives(self, tmp_path):
        """A subfield's count IS a distinct initiative count, so say so."""
        data = make_data(tmp_path, [BASE_ROW, TWO_FIELD_ROW])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        _, regions = treemap_coverage_svg(data, tax_p)

        tips = [tip for *_, tip in regions]
        assert any(t == "Hydrology: 2 partnership initiatives" for t in tips)
        assert any(t == "Climatology: 1 partnership initiative" for t in tips)

    def test_cells_with_no_partnerships_are_labelled(self, tmp_path):
        data = make_data(tmp_path, [BASE_ROW])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        _, regions = treemap_coverage_svg(data, tax_p)

        tips = [tip for *_, tip in regions]
        assert f"Meteorology: {content.TERM_NO_PARTNERSHIPS_LOWER}" in tips

    def test_category_headers_say_field_tags(self, tmp_path):
        """Category totals sum subfield counts, so they double-count initiatives."""
        data = make_data(tmp_path, [BASE_ROW, TWO_FIELD_ROW])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        svg, _ = treemap_coverage_svg(data, tax_p)

        assert "field tag" in svg
        assert ">PARTNERSHIPS<" not in svg

    def test_browser_treemap_shares_the_same_vocabulary(self, tmp_path):
        """The HTML and SVG renderers must not drift apart on wording."""
        data = make_data(tmp_path)
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        html = treemap_coverage(data, tax_p)

        assert "window.DWR_TERMS" in html
        assert content.TERM_INITIATIVES in html
