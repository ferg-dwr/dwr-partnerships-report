"""
treemaps.py — Plotly treemap chart generators.

All functions accept a PartnershipData instance and return a Plotly Figure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px

from dwr_report.ingest.loader import PartnershipData, normalize_colname


def treemap(
    data: PartnershipData,
    path: list[str],
    values: str | None = None,
    title: str = "Treemap",
    color: str | None = None,
) -> Any:
    """
    Generate an interactive treemap chart.

    Columns in `path` containing lists are automatically parsed and exploded.
    If no values column is provided, defaults to counting partnerships.

    :param data:   PartnershipData instance
    :param path:   List of column names defining the hierarchy,
                   e.g. ['1st Level Science Category', 'Science and Technology Fields']
    :param values: Optional numeric column for block size.
                   Defaults to partnership count when None.
    :param title:  Chart title
    :param color:  Optional column name for continuous color scaling
    :return:       Plotly Figure
    """
    df_plot = data.prepare_plot_df(path)

    if values is None:
        df_plot["_count"] = 1
        values = "_count"
    elif values not in df_plot.columns:
        raise ValueError(f"Column '{values}' not found. Available: {df_plot.columns.tolist()}")

    fig = px.treemap(
        df_plot,
        path=path,
        values=values,
        color=color,
        title=title,
        color_continuous_scale="Blues",
    )

    fig.update_traces(
        textinfo="label+value+percent root",
        hovertemplate="<b>%{label}</b><br>Partnerships: %{value}<br>% of Total: %{percentRoot:.1%}",
    )

    fig.update_layout(
        title_font_size=20,
        margin=dict(t=50, l=10, r=10, b=10),
    )

    return fig


def treemap_coverage(
    data: PartnershipData,
    taxonomy_path: str | Path,
    title: str = "DWR Science Partnership Coverage (Grey = Gap; Darker Blue = More Partnerships)",
) -> Any:
    """
    Generate a coverage treemap built from the taxonomy as the base,
    so that fields with zero partnerships are still represented (shown in grey).

    Darker blue = more partnerships. Grey = gap (no partnerships).
    Requires enrich_science_fields() to have been called first on `data`.

    :param data:          PartnershipData instance (must be enriched)
    :param taxonomy_path: Path to the taxonomy CSV
    :param title:         Chart title
    :return:              Plotly Figure
    """
    import numpy as np

    taxonomy = pd.read_csv(taxonomy_path, dtype=str)
    taxonomy.columns = [normalize_colname(c) for c in taxonomy.columns]
    taxonomy = taxonomy.rename(columns={"2nd level (Science Field)": "2nd Level (Science Field)"})

    path_cols = ["1st Level (Science Category)", "2nd Level (Science Field)"]
    for col in path_cols:
        taxonomy[col] = taxonomy[col].astype(str).str.strip()

    taxonomy = taxonomy.replace({"nan": pd.NA, "": pd.NA})
    taxonomy = taxonomy.dropna(subset=path_cols).copy()

    field_counts = (
        data.df["Science and Technology Fields"]
        .explode()
        .dropna()
        .astype(str)
        .str.strip()
        .value_counts()
    )

    taxonomy["Count"] = (
        taxonomy["2nd Level (Science Field)"]
        .astype(str)
        .str.strip()
        .map(field_counts)
        .fillna(0)
        .astype(int)
    )

    max_count = taxonomy["Count"].max()
    taxonomy["NormCount"] = taxonomy["Count"] / max_count if max_count > 0 else 0.01
    taxonomy["ColorValue"] = taxonomy["NormCount"]
    taxonomy.loc[taxonomy["Count"] == 0, "ColorValue"] = -0.01
    taxonomy["Size"] = taxonomy["Count"].where(taxonomy["Count"] > 0, 1)

    color_scale = [
        [0.0, "#D9D9D9"],
        [0.01, "#DEEBF7"],
        [0.5, "#6BAED6"],
        [1.0, "#084594"],
    ]

    fig = px.treemap(
        taxonomy,
        path=path_cols,
        values="Size",
        color="ColorValue",
        color_continuous_scale=color_scale,
        range_color=(-0.01, 1.0),
    )

    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>Partnerships: %{customdata[0]}<extra></extra>",
        customdata=np.stack([taxonomy["Count"]], axis=-1),
        textinfo="label",
    )

    fig.update_layout(
        width=1100,
        height=900,
        margin=dict(t=10, l=20, r=20, b=20),
        coloraxis_showscale=False,
        title_font_size=20,
    )

    return fig
