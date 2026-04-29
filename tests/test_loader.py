"""
tests/test_loader.py — Unit tests for dwr_report.data.loader.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dwr_report.ingest.loader import (
    LIST_LIKE_COLUMNS,
    PartnershipData,
    normalize_colname,
    to_list_if_listlike,
)

BASE_ROW = {
    "ID": 1,
    "Partnership Organization Name": '["UC Davis"]',
    "Organization Type": '["University"]',
    "Relevant DWR Program(s) and/ or Project(s)": '["Delta Science"]',
    "Partnership Type": '["Research"]',
    "Status of Partnership": '["Active"]',
    "DWR Investments": '["Funding"]',
    "Science and Technology Fields": '["Hydrology", "Ecology"]',
    "DWR Division/ Office/ Branch": "Flood Operations",
    "Main DWR Point of Contact": "Smith, Jane@DWR",
}


def write_csv(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    p = tmp_path / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


class TestNormalizeColname:
    def test_strips_leading_trailing(self):
        assert normalize_colname("  ID  ") == "ID"

    def test_collapses_internal_spaces(self):
        assert normalize_colname("DWR  Division /  Branch") == "DWR Division / Branch"

    def test_no_change_needed(self):
        assert normalize_colname("Partnership Type") == "Partnership Type"


class TestToListIfListlike:
    def test_json_list_string(self):
        assert to_list_if_listlike('["A", "B"]') == ["A", "B"]

    def test_python_list_string(self):
        assert to_list_if_listlike("['A', 'B']") == ["A", "B"]

    def test_already_a_list(self):
        assert to_list_if_listlike(["A", "B"]) == ["A", "B"]

    def test_empty_string(self):
        assert to_list_if_listlike("") == []

    def test_nan_returns_empty_list(self):
        assert to_list_if_listlike(float("nan")) == []

    def test_plain_string_unchanged(self):
        assert to_list_if_listlike("Jane Smith") == "Jane Smith"

    def test_strips_whitespace_from_items(self):
        assert to_list_if_listlike('["  A  ", " B"]') == ["A", "B"]

    def test_filters_empty_items(self):
        assert to_list_if_listlike('["A", "", "B"]') == ["A", "B"]

    def test_single_item_list(self):
        assert to_list_if_listlike('["UC Davis"]') == ["UC Davis"]


class TestPartnershipDataLoad:
    def test_loads_csv(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        data = PartnershipData(p)
        assert len(data.df) == 1

    def test_rejects_non_csv(self, tmp_path):
        p = tmp_path / "data.xlsx"
        p.write_text("fake")
        with pytest.raises(ValueError, match="Only CSV files"):
            PartnershipData(p)

    def test_rejects_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PartnershipData(tmp_path / "nonexistent.csv")

    def test_id_coerced_to_numeric(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        data = PartnershipData(p)
        assert pd.api.types.is_numeric_dtype(data.df["ID"])

    def test_list_like_columns_parsed(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        data = PartnershipData(p)
        for col in LIST_LIKE_COLUMNS:
            if col in data.df.columns:
                val = data.df[col].iloc[0]
                assert isinstance(val, list), f"Expected list for '{col}', got {type(val)}"

    def test_column_whitespace_normalized(self, tmp_path):
        row = {"  ID  ": 1, "  Partnership Organization Name  ": '["UC Davis"]'}
        p = write_csv(tmp_path, "data.csv", [row])
        data = PartnershipData(p)
        assert "ID" in data.df.columns
        assert "Partnership Organization Name" in data.df.columns

    def test_cell_whitespace_stripped(self, tmp_path):
        row = {**BASE_ROW, "Main DWR Point of Contact": "  Smith, Jane@DWR  "}
        p = write_csv(tmp_path, "data.csv", [row])
        data = PartnershipData(p)
        assert data.df["Main DWR Point of Contact"].iloc[0] == "Smith, Jane@DWR"

    def test_multiple_rows(self, tmp_path):
        rows = [{**BASE_ROW, "ID": i} for i in range(1, 6)]
        p = write_csv(tmp_path, "data.csv", rows)
        data = PartnershipData(p)
        assert len(data.df) == 5

    def test_preview_returns_head(self, tmp_path):
        rows = [{**BASE_ROW, "ID": i} for i in range(1, 11)]
        p = write_csv(tmp_path, "data.csv", rows)
        data = PartnershipData(p)
        assert len(data.preview(3)) == 3
        assert len(data.preview()) == 5


class TestPrepareplotDf:
    def test_explodes_list_column(self, tmp_path):
        row = {**BASE_ROW, "Science and Technology Fields": '["Hydrology", "Ecology"]'}
        p = write_csv(tmp_path, "data.csv", [row])
        data = PartnershipData(p)
        df = data.prepare_plot_df(["Science and Technology Fields"])
        assert len(df) == 2
        assert set(df["Science and Technology Fields"]) == {"Hydrology", "Ecology"}

    def test_drops_null_rows(self, tmp_path):
        rows = [
            {**BASE_ROW, "ID": 1, "Science and Technology Fields": '["Hydrology"]'},
            {**BASE_ROW, "ID": 2, "Science and Technology Fields": None},
        ]
        p = write_csv(tmp_path, "data.csv", rows)
        data = PartnershipData(p)
        df = data.prepare_plot_df(["Science and Technology Fields"])
        assert len(df) == 1
        assert df["ID"].iloc[0] == 1

    def test_raises_on_missing_column(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        data = PartnershipData(p)
        with pytest.raises(ValueError, match="not found"):
            data.prepare_plot_df(["Nonexistent Column"])

    def test_plain_string_column_not_exploded(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        data = PartnershipData(p)
        df = data.prepare_plot_df(["Main DWR Point of Contact"])
        assert len(df) == 1


class TestExplodeColumn:
    def test_explodes_correctly(self, tmp_path):
        row = {**BASE_ROW, "Science and Technology Fields": '["Hydrology", "Ecology", "Snow"]'}
        p = write_csv(tmp_path, "data.csv", [row])
        data = PartnershipData(p)
        exploded = data.explode_column("Science and Technology Fields")
        assert len(exploded) == 3

    def test_original_df_unchanged(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        data = PartnershipData(p)
        original_len = len(data.df)
        data.explode_column("Science and Technology Fields")
        assert len(data.df) == original_len
