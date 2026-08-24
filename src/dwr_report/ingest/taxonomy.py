"""
taxonomy.py — Science field taxonomy loading and enrichment.

Maps 2nd-level science fields to 1st-level science categories
using the DWR custom taxonomy CSV.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from dwr_report.ingest.loader import PartnershipData


def load_taxonomy(taxonomy_path: str | Path) -> dict[str, str]:
    """
    Load the taxonomy CSV and return a lookup dict:
        { '2nd level field': '1st level category' }
    """
    tax = pd.read_csv(taxonomy_path, dtype=str)[
        ["1st Level (Science Category)", "2nd level (Science Field)"]
    ].dropna()
    return dict(
        zip(
            tax["2nd level (Science Field)"].str.strip(),
            tax["1st Level (Science Category)"].str.strip(),
            strict=False,
        )
    )


def enrich_science_fields(data: PartnershipData, taxonomy_path: str | Path) -> None:
    """
    Adds a '1st Level Science Category' column to data.df by mapping
    'Science and Technology Fields' through the taxonomy lookup.
    Modifies data.df in place.

    :param data:          PartnershipData instance to enrich
    :param taxonomy_path: Path to the taxonomy CSV
    """
    lookup = load_taxonomy(taxonomy_path)

    def map_to_category(fields: Any) -> Any:
        if not isinstance(fields, list) or len(fields) == 0:
            return None
        categories: list[str] = []
        for field in fields:
            cat = lookup.get(field.strip(), "Uncategorized")
            if cat not in categories:
                categories.append(cat)
        return categories[0] if len(categories) == 1 else categories

    data.df["1st Level Science Category"] = data.df["Science and Technology Fields"].map(
        map_to_category
    )

    uncategorized = data.df[
        data.df["1st Level Science Category"].apply(
            lambda x: x == "Uncategorized" if not isinstance(x, list) else "Uncategorized" in x
        )
    ]
    if len(uncategorized) > 0:
        print(f"  {len(uncategorized)} rows have unmapped fields -- flagged as 'Uncategorized'")

    print("'1st Level Science Category' column added")
