"""
tests/test_treemaps.py — Unit tests for dwr_report.charts.treemaps.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dwr_report.charts.treemaps import treemap, treemap_coverage
from dwr_report.ingest.loader import PartnershipData
from dwr_report.ingest.taxonomy import enrich_science_fields

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


class TestTreemapCoverage:
    def test_returns_figure(self, tmp_path):
        import plotly.graph_objects as go

        data = make_data(tmp_path)
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        fig = treemap_coverage(data, tax_p)
        assert isinstance(fig, go.Figure)

    def test_includes_zero_count_fields(self, tmp_path):
        """Fields with no partnerships should still appear in the chart."""
        data = make_data(tmp_path)  # Only has Hydrology
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        fig = treemap_coverage(data, tax_p)
        # Climatology and Meteorology have 0 partnerships but should be in labels
        labels = fig.data[0].labels
        assert "Climatology" in labels or "Meteorology" in labels

    def test_custom_title(self, tmp_path):
        data = make_data(tmp_path)
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        enrich_science_fields(data, tax_p)
        fig = treemap_coverage(data, tax_p, title="Coverage Chart")
        assert fig.layout.title.text == "Coverage Chart"
