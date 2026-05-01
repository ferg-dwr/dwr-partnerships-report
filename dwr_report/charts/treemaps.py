"""
treemaps.py — Treemap chart generators.

treemap()          — Plotly treemap for ad-hoc notebook use.
treemap_coverage() — Custom SVG treemap (squarified layout, React/Babel)
                     rendered from templates/treemap_coverage.html.
                     Returns a self-contained HTML string.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
from jinja2 import Environment, FileSystemLoader

from dwr_report.ingest.loader import PartnershipData, normalize_colname

TREEMAP_TEMPLATE = Path("templates/treemap_coverage.html")


def treemap(
    data: PartnershipData,
    path: list[str],
    values: str | None = None,
    title: str = "Treemap",
    color: str | None = None,
) -> Any:
    """
    Generate an interactive Plotly treemap.

    Columns in `path` containing lists are automatically parsed and exploded.
    If no values column is provided, defaults to counting partnerships.

    :param data:   PartnershipData instance
    :param path:   List of column names defining the hierarchy
    :param values: Optional numeric column for block size
    :param title:  Chart title
    :param color:  Optional column for continuous color scaling
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
    fig.update_layout(title_font_size=20, margin=dict(t=50, l=10, r=10, b=10))
    return fig


def _build_taxonomy_json(
    data: PartnershipData,
    taxonomy_path: str | Path,
) -> list[dict]:
    """
    Build the DWR_TAXONOMY structure from the taxonomy CSV and partnership data.

    Returns [{category, subfields:[{name, count}]}] for injection into the template.
    """
    taxonomy = pd.read_csv(taxonomy_path, dtype=str)
    taxonomy.columns = [normalize_colname(c) for c in taxonomy.columns]
    taxonomy = taxonomy.rename(columns={"2nd level (Science Field)": "2nd Level (Science Field)"})

    path_cols = ["1st Level (Science Category)", "2nd Level (Science Field)"]
    for col in path_cols:
        taxonomy[col] = taxonomy[col].astype(str).str.strip()

    taxonomy = taxonomy.replace({"nan": pd.NA, "": pd.NA})
    taxonomy = taxonomy.dropna(subset=path_cols).copy()

    # Count partnerships per science field
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

    result: list[dict] = []
    for cat, group in taxonomy.groupby("1st Level (Science Category)", sort=False):
        subfields = [
            {"name": row["2nd Level (Science Field)"], "count": int(row["Count"])}
            for _, row in group.iterrows()
        ]
        result.append({"category": str(cat), "subfields": subfields})

    return result


def treemap_coverage(
    data: PartnershipData,
    taxonomy_path: str | Path,
    template_path: Path = TREEMAP_TEMPLATE,
) -> str:
    """
    Generate a coverage treemap as a self-contained HTML string.

    Uses a custom squarified SVG layout (React + Babel, no Plotly).
    The treemap grows vertically as the taxonomy expands — no horizontal squishing.

    Blue hues (light → dark) = 1 → N partnerships.
    Grey hatched cells = coverage gaps (0 partnerships).
    Click a category header to zoom in; Esc or click header to zoom out.

    :param data:          PartnershipData instance (must be enriched)
    :param taxonomy_path: Path to dwr_custom_taxonomy.csv
    :param template_path: Jinja2 template path
    :return:              Self-contained HTML string
    """
    taxonomy_json = _build_taxonomy_json(data, taxonomy_path)

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,
    )
    template = env.get_template(template_path.name)
    return template.render(taxonomy_json=taxonomy_json)
