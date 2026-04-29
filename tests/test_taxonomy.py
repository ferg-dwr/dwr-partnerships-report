"""
tests/test_taxonomy.py — Unit tests for dwr_report.data.taxonomy.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dwr_report.ingest.loader import PartnershipData
from dwr_report.ingest.taxonomy import enrich_science_fields, load_taxonomy

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
        "1st Level (Science Category)": "Atmospheric Sciences",
        "2nd level (Science Field)": "Climatology",
        "Description": "Study of climate.",
    },
    {
        "1st Level (Science Category)": "Atmospheric Sciences",
        "2nd level (Science Field)": "Meteorology",
        "Description": "Study of weather.",
    },
    {
        "1st Level (Science Category)": "Geological and Earth Sciences",
        "2nd level (Science Field)": "Hydrology",
        "Description": "Study of water.",
    },
    {
        "1st Level (Science Category)": "Biological and Ecological Sciences",
        "2nd level (Science Field)": "Aquatic Ecology",
        "Description": "Study of aquatic ecosystems.",
    },
]


def write_csv(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    p = tmp_path / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


class TestLoadTaxonomy:
    def test_returns_dict(self, tmp_path):
        p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        lookup = load_taxonomy(p)
        assert isinstance(lookup, dict)

    def test_correct_mapping(self, tmp_path):
        p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        lookup = load_taxonomy(p)
        assert lookup["Hydrology"] == "Geological and Earth Sciences"
        assert lookup["Climatology"] == "Atmospheric Sciences"

    def test_strips_whitespace(self, tmp_path):
        rows = [
            {
                "1st Level (Science Category)": "  Atmospheric Sciences  ",
                "2nd level (Science Field)": "  Climatology  ",
                "Description": "",
            }
        ]
        p = write_csv(tmp_path, "tax.csv", rows)
        lookup = load_taxonomy(p)
        assert lookup["Climatology"] == "Atmospheric Sciences"

    def test_drops_nan_rows(self, tmp_path):
        rows = [
            *TAXONOMY_ROWS,
            {"1st Level (Science Category)": None, "2nd level (Science Field)": None},
        ]
        p = write_csv(tmp_path, "tax.csv", rows)
        lookup = load_taxonomy(p)
        assert None not in lookup


class TestEnrichScienceFields:
    def test_adds_category_column(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = PartnershipData(p)
        enrich_science_fields(data, tax_p)
        assert "1st Level Science Category" in data.df.columns

    def test_correct_single_category(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = PartnershipData(p)
        enrich_science_fields(data, tax_p)
        assert data.df["1st Level Science Category"].iloc[0] == "Geological and Earth Sciences"

    def test_multiple_fields_same_category_returns_string(self, tmp_path):
        row = {**BASE_ROW, "Science and Technology Fields": '["Climatology", "Meteorology"]'}
        p = write_csv(tmp_path, "data.csv", [row])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = PartnershipData(p)
        enrich_science_fields(data, tax_p)
        # Both map to Atmospheric Sciences — should return a single string
        assert data.df["1st Level Science Category"].iloc[0] == "Atmospheric Sciences"

    def test_multiple_fields_different_categories_returns_list(self, tmp_path):
        row = {**BASE_ROW, "Science and Technology Fields": '["Hydrology", "Climatology"]'}
        p = write_csv(tmp_path, "data.csv", [row])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = PartnershipData(p)
        enrich_science_fields(data, tax_p)
        result = data.df["1st Level Science Category"].iloc[0]
        assert isinstance(result, list)
        assert "Geological and Earth Sciences" in result
        assert "Atmospheric Sciences" in result

    def test_unmapped_field_flagged_as_uncategorized(self, tmp_path):
        row = {**BASE_ROW, "Science and Technology Fields": '["Unknown Field XYZ"]'}
        p = write_csv(tmp_path, "data.csv", [row])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = PartnershipData(p)
        enrich_science_fields(data, tax_p)
        assert data.df["1st Level Science Category"].iloc[0] == "Uncategorized"

    def test_empty_fields_returns_none(self, tmp_path):
        row = {**BASE_ROW, "Science and Technology Fields": "[]"}
        p = write_csv(tmp_path, "data.csv", [row])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = PartnershipData(p)
        enrich_science_fields(data, tax_p)
        assert data.df["1st Level Science Category"].iloc[0] is None

    def test_modifies_df_in_place(self, tmp_path):
        p = write_csv(tmp_path, "data.csv", [BASE_ROW])
        tax_p = write_csv(tmp_path, "tax.csv", TAXONOMY_ROWS)
        data = PartnershipData(p)
        original_id = id(data.df)
        enrich_science_fields(data, tax_p)
        assert id(data.df) == original_id
