"""
loader.py — Partnership CSV loading and normalization.

Handles reading, cleaning, and preparing the DWR partnerships dataset.
Chart modules receive a PartnershipData instance rather than owning I/O.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pandas as pd

# Columns stored as JSON-like list strings in the CSV export
LIST_LIKE_COLUMNS = [
    "Partnership Organization Name",
    "Organization Type",
    "Relevant DWR Program(s) and/ or Project(s)",
    "Partnership Type",
    "Status of Partnership",
    "DWR Investments",
    "Science and Technology Fields",
]

# NOTE: "DWR Division/ Office/ Branch" is intentionally excluded from
# LIST_LIKE_COLUMNS — confirmed to be a plain string in Microsoft Lists exports.


def normalize_colname(col: str) -> str:
    """Strip and collapse whitespace in a column name."""
    return " ".join(str(col).strip().split())


def to_list_if_listlike(x: Any) -> Any:
    """
    Convert strings that look like Python/JSON lists into Python lists.
    '["UC Davis"]'  -> ["UC Davis"]
    "['A', 'B']"    -> ["A", "B"]
    Leaves everything else unchanged.
    """
    if isinstance(x, list):
        return x
    if pd.isna(x):
        return []
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip() != ""]
            except Exception:
                return x
    return x


class PartnershipData:
    """
    Loads and normalizes the DWR partnerships CSV.

    Attributes:
        csv_path: Path to the source CSV file.
        df:       Normalized DataFrame, ready for charting.
    """

    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self.df = self._load()

    def _load(self) -> pd.DataFrame:
        """
        Load, validate, and normalize the CSV file.
        - Enforces .csv extension
        - Reads all columns as strings to prevent type mangling
        - Normalizes column name whitespace
        - Strips whitespace from all string cells
        - Parses LIST_LIKE_COLUMNS into Python lists
        - Coerces ID to numeric
        """
        if self.csv_path.suffix.lower() != ".csv":
            raise ValueError(f"Only CSV files are supported. Got: '{self.csv_path.suffix}'")
        if not self.csv_path.exists():
            raise FileNotFoundError(f"File not found: '{self.csv_path}'")

        df = pd.read_csv(self.csv_path, dtype=str)
        df.columns = [normalize_colname(c) for c in df.columns]

        for col in df.columns:
            df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)

        for col in LIST_LIKE_COLUMNS:
            if col in df.columns:
                df[col] = df[col].map(to_list_if_listlike)

        if "ID" in df.columns:
            df["ID"] = pd.to_numeric(df["ID"], errors="coerce")

        print(f"Loaded '{self.csv_path.name}' — {len(df)} rows, {len(df.columns)} columns")
        return df

    def prepare_plot_df(self, columns: list[str]) -> pd.DataFrame:
        """
        Returns a clean copy of self.df ready for plotting:
        - Parses and explodes any list-valued columns in `columns`
        - Drops rows where any of those columns are null
        - Resets the index
        """
        df_plot = self.df.copy()

        for col in columns:
            if col not in df_plot.columns:
                raise ValueError(f"Column '{col}' not found. Available: {df_plot.columns.tolist()}")
            df_plot[col] = df_plot[col].map(to_list_if_listlike)
            if df_plot[col].apply(lambda x: isinstance(x, list)).any():
                df_plot = df_plot.explode(col)

        return df_plot.dropna(subset=columns).reset_index(drop=True)

    def preview(self, rows: int = 5) -> pd.DataFrame:
        """Preview the loaded DataFrame."""
        return self.df.head(rows)

    def explode_column(self, column: str) -> pd.DataFrame:
        """
        Returns a copy of the DataFrame with the given list column
        exploded into one row per value.

        :param column: Column name to explode
        :return: Exploded DataFrame
        """
        df_copy = self.df.copy()
        df_copy[column] = df_copy[column].map(to_list_if_listlike)
        df_copy = df_copy.explode(column).reset_index(drop=True)
        print(f"Exploded '{column}': {len(self.df)} -> {len(df_copy)} rows")
        return df_copy
