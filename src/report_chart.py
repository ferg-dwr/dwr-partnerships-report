"""
report_chart.py — DWR Partnerships report chart generator.

Loads a DWR partnerships CSV and generates interactive Plotly charts
and vis.js network graphs via Jinja2 HTML templates.
"""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

# vis-network CDN — used in place of bundling the JS locally
_VIS_JS_CDN = "https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js"


class ReportChart:
    """
    Loads a DWR partnerships CSV and generates interactive Plotly charts.
    """

    # Columns stored as JSON-like list strings in the CSV export
    LIST_LIKE_COLUMNS: ClassVar[list[str]] = [
        "Partnership Organization Name",
        "Organization Type",
        "Relevant DWR Program(s) and/ or Project(s)",
        "Partnership Type",
        "Status of Partnership",
        "DWR Investments",
        "Science and Technology Fields",
    ]

    def __init__(self, csv_path: str | Path):
        """
        Initialize ReportChart with a CSV file path.

        :param csv_path: Path to the CSV file (must be .csv)
        """
        self.csv_path = Path(csv_path)
        self.df = self._load_csv()
        self.df_exploded: dict[str, pd.DataFrame] = {}

    @staticmethod
    def _normalize_colname(col: str) -> str:
        """Strip and collapse whitespace in a column name."""
        return " ".join(str(col).strip().split())

    @staticmethod
    def _to_list_if_listlike(x: Any) -> Any:
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

    def _load_csv(self) -> pd.DataFrame:
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

        # Normalize column names
        df.columns = [self._normalize_colname(c) for c in df.columns]

        # Strip whitespace from all string cells
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

        # Parse list-like columns
        for col in self.LIST_LIKE_COLUMNS:
            if col in df.columns:
                df[col] = df[col].map(self._to_list_if_listlike)

        # Coerce ID to numeric
        if "ID" in df.columns:
            df["ID"] = pd.to_numeric(df["ID"], errors="coerce")

        print(f"Loaded '{self.csv_path.name}' — {len(df)} rows, {len(df.columns)} columns")
        return df

    def _prepare_plot_df(self, columns: list) -> pd.DataFrame:
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
            df_plot[col] = df_plot[col].map(self._to_list_if_listlike)
            if df_plot[col].apply(lambda x: isinstance(x, list)).any():
                df_plot = df_plot.explode(col)

        df_plot = df_plot.dropna(subset=columns).reset_index(drop=True)
        return df_plot

    def preview(self, rows: int = 5) -> pd.DataFrame:
        """Preview the loaded DataFrame."""
        return self.df.head(rows)

    def explode_column(self, column: str) -> pd.DataFrame:
        """
        Returns a copy of the DataFrame with the given list column
        exploded into one row per value. Result is cached in self.df_exploded.

        :param column: Column name to explode
        :return: Exploded DataFrame
        """
        if column not in self.df_exploded:
            df_copy = self.df.copy()
            df_copy[column] = df_copy[column].map(self._to_list_if_listlike)
            df_copy = df_copy.explode(column).reset_index(drop=True)
            self.df_exploded[column] = df_copy
            print(f"Exploded '{column}': {len(self.df)} -> {len(df_copy)} rows")
        return self.df_exploded[column]

    def _load_taxonomy(self, taxonomy_path: str | Path) -> dict:
        """
        Builds a lookup dict: { '2nd level field': '1st level category' }
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

    def enrich_science_fields(self, taxonomy_path: str | Path) -> None:
        """
        Adds a '1st Level Science Category' column to self.df by mapping
        'Science and Technology Fields' through the taxonomy lookup.
        Modifies self.df in place.
        """
        lookup = self._load_taxonomy(taxonomy_path)

        def map_to_category(fields: Any) -> Any:
            if not isinstance(fields, list) or len(fields) == 0:
                return None
            categories = []
            for field in fields:
                cat = lookup.get(field.strip(), "Uncategorized")
                if cat not in categories:
                    categories.append(cat)
            return categories[0] if len(categories) == 1 else categories

        self.df["1st Level Science Category"] = self.df["Science and Technology Fields"].map(
            map_to_category
        )

        uncategorized = self.df[
            self.df["1st Level Science Category"].apply(
                lambda x: x == "Uncategorized" if not isinstance(x, list) else "Uncategorized" in x
            )
        ]
        if len(uncategorized) > 0:
            print(f"  {len(uncategorized)} rows have unmapped fields -- flagged as 'Uncategorized'")

        print("'1st Level Science Category' column added")

    def treemap(
        self,
        path: list,
        values: str | None = None,
        title: str = "Treemap",
        color: str | None = None,
    ) -> Any:
        """
        Generate an interactive treemap chart.

        path columns containing lists are automatically parsed and exploded.
        If no values column is provided, defaults to counting partnerships.

        :param path:   List of column names defining the hierarchy
        :param values: Optional numeric column for block size
        :param title:  Chart title
        :param color:  Optional column name for continuous color scaling
        :return:       Plotly Figure
        """
        import plotly.express as px

        df_plot = self._prepare_plot_df(path)

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
        self,
        taxonomy_path: str | Path,
        title: str = "DWR Science Partnership Coverage (Grey = Gap; Darker Blue = More Partnerships)",
    ) -> Any:
        """
        Generate a coverage treemap built from the taxonomy as the base,
        so that fields with zero partnerships are still represented (shown in grey).

        Darker blue = more partnerships. Grey = gap (no partnerships).
        Requires enrich_science_fields() to have been called first.

        :param taxonomy_path: Path to the taxonomy CSV
        :param title:         Chart title
        :return:              Plotly Figure
        """
        import numpy as np
        import plotly.express as px

        taxonomy = pd.read_csv(taxonomy_path, dtype=str)
        taxonomy.columns = [self._normalize_colname(c) for c in taxonomy.columns]
        taxonomy = taxonomy.rename(
            columns={"2nd level (Science Field)": "2nd Level (Science Field)"}
        )

        path_cols = ["1st Level (Science Category)", "2nd Level (Science Field)"]
        for col in path_cols:
            taxonomy[col] = taxonomy[col].astype(str).str.strip()

        taxonomy = taxonomy.replace({"nan": pd.NA, "": pd.NA})
        taxonomy = taxonomy.dropna(subset=path_cols).copy()

        field_counts = (
            self.df["Science and Technology Fields"]
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
            title=title,
        )

        fig.update_traces(
            hovertemplate="<b>%{label}</b><br>Partnerships: %{customdata[0]}<extra></extra>",
            customdata=np.stack([taxonomy["Count"]], axis=-1),
            textinfo="label",
        )

        fig.update_layout(
            width=1100,
            height=900,
            margin=dict(t=80, l=20, r=20, b=20),
            coloraxis_showscale=False,
            title_font_size=20,
        )
        return fig

    def network_tripartite(
        self,
        template_path: str | Path = "templates/network_tripartite.html",
        title: str = "Science Field <-> Staff <-> Division Network",
    ) -> str:
        """
        Generate an interactive tripartite network graph.
        Requires enrich_science_fields() to have been called first.

        :param template_path: Path to the Jinja2 HTML template
        :param title:         Chart title
        :return:              Rendered HTML string
        """
        from jinja2 import Environment, FileSystemLoader

        staff_col = "Main DWR Point of Contact"
        division_col = "DWR Division/ Office/ Branch"
        fields_col = "Science and Technology Fields"
        category_col = "1st Level Science Category"

        if category_col not in self.df.columns:
            raise ValueError(
                f"'{category_col}' column not found. "
                "Please run enrich_science_fields() before calling network_tripartite()."
            )

        df = self.df[[staff_col, division_col, fields_col, category_col]].copy()
        df[fields_col] = df[fields_col].map(self._to_list_if_listlike)
        df[division_col] = df[division_col].map(self._to_list_if_listlike)
        df[category_col] = df[category_col].map(self._to_list_if_listlike)
        df = df.explode(fields_col).explode(division_col).explode(category_col)
        df = df.dropna(subset=[staff_col, division_col, fields_col, category_col])
        df = df.apply(lambda col: col.str.strip() if col.dtype == "object" else col)

        field_staff_edges = df[[fields_col, staff_col]].drop_duplicates().values.tolist()
        staff_division_edges = df[[staff_col, division_col]].drop_duplicates().values.tolist()

        field_to_category = (
            df[[fields_col, category_col]]
            .drop_duplicates()
            .groupby(fields_col)[category_col]
            .first()
            .to_dict()
        )

        categories = sorted(set(field_to_category.values()))
        CATEGORY_PALETTE = [
            "#1E88E5",
            "#43A047",
            "#E53935",
            "#8E24AA",
            "#F4511E",
            "#00ACC1",
            "#FFB300",
            "#6D4C41",
            "#00897B",
            "#D81B60",
            "#3949AB",
        ]
        category_colors = {
            cat: CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)] for i, cat in enumerate(categories)
        }

        fields_by_category: dict[str, list] = defaultdict(list)
        for field, cat in sorted(field_to_category.items()):
            fields_by_category[cat].append(field)
        for cat in fields_by_category:
            fields_by_category[cat].sort()

        divisions = sorted(df[division_col].unique().tolist())
        staff = sorted(df[staff_col].unique().tolist())

        CANVAS_HEIGHT = 4000
        X_FIELD = -700
        X_STAFF = 0
        X_DIVISION = 700
        PADDING = 60
        GROUP_GAP = 80
        DOT_SIZE = 14
        STAFF_COLOR = "#81C784"
        DIVISION_COLOR = "#FFB74D"
        DIM_COLOR = "#e8e8e8"
        GLOW_COLOR = "#FFD700"

        def spread_evenly(items: list) -> list:
            n = len(items)
            if n == 1:
                return [CANVAS_HEIGHT // 2]
            step = (CANVAS_HEIGHT - 2 * PADDING) / (n - 1)
            return [int(PADDING + i * step) for i in range(n)]

        staff_positions = {s: y for s, y in zip(staff, spread_evenly(staff), strict=False)}
        division_positions = {
            d: y for d, y in zip(divisions, spread_evenly(divisions), strict=False)
        }

        field_positions: dict[str, int] = {}
        field_node_colors: dict[str, str] = {}
        total_fields = sum(len(v) for v in fields_by_category.values())
        total_gaps = (len(fields_by_category) - 1) * GROUP_GAP
        usable_height = CANVAS_HEIGHT - 2 * PADDING - total_gaps
        field_spacing = usable_height / max(total_fields - 1, 1)

        y_cursor = float(PADDING)
        for cat in categories:
            for field in fields_by_category[cat]:
                field_positions[field] = int(y_cursor)
                field_node_colors[field] = category_colors[cat]
                y_cursor += field_spacing
            y_cursor += GROUP_GAP

        nodes = []
        for field, y in field_positions.items():
            color = field_node_colors[field]
            nodes.append(
                {
                    "id": field,
                    "label": "",
                    "x": X_FIELD,
                    "y": y,
                    "size": DOT_SIZE,
                    "shape": "dot",
                    "color": {"background": color, "border": color},
                    "font": {"size": 0},
                    "borderWidth": 0,
                    "fixed": True,
                    "group": "field",
                }
            )
        for s, y in staff_positions.items():
            nodes.append(
                {
                    "id": s,
                    "label": "",
                    "x": X_STAFF,
                    "y": y,
                    "size": DOT_SIZE,
                    "shape": "dot",
                    "color": {"background": STAFF_COLOR, "border": STAFF_COLOR},
                    "font": {"size": 0},
                    "borderWidth": 0,
                    "fixed": True,
                    "group": "staff",
                }
            )
        for d, y in division_positions.items():
            nodes.append(
                {
                    "id": d,
                    "label": d,
                    "x": X_DIVISION,
                    "y": y,
                    "size": DOT_SIZE + 4,
                    "shape": "dot",
                    "color": {"background": DIVISION_COLOR, "border": DIVISION_COLOR},
                    "font": {"size": 13, "color": "#333333", "background": "#ffffffcc"},
                    "borderWidth": 0,
                    "fixed": True,
                    "group": "division",
                }
            )

        edges = []
        for i, (f, s) in enumerate(field_staff_edges):
            edges.append(
                {
                    "id": f"e{i}",
                    "from": f,
                    "to": s,
                    "color": {"color": "rgba(180,180,180,0.4)"},
                    "width": 1.2,
                }
            )
        offset = len(field_staff_edges)
        for i, (s, d) in enumerate(staff_division_edges):
            edges.append(
                {
                    "id": f"e{offset + i}",
                    "from": s,
                    "to": d,
                    "color": {"color": "rgba(180,180,180,0.4)"},
                    "width": 1.2,
                }
            )

        all_node_ids = list(field_positions) + staff + divisions
        adjacency: dict[str, list] = {n: [] for n in all_node_ids}
        for f, s in field_staff_edges:
            adjacency[f].append(s)
            adjacency[s].append(f)
        for s, d in staff_division_edges:
            adjacency[s].append(d)
            adjacency[d].append(s)
        adjacency = {k: list(set(v)) for k, v in adjacency.items()}

        node_meta: dict[str, dict] = {}
        for f in field_positions:
            node_meta[f] = {
                "type": "field",
                "category": field_to_category[f],
                "color": field_node_colors[f],
            }
        for s in staff:
            node_meta[s] = {"type": "staff", "color": STAFF_COLOR}
        for d in divisions:
            node_meta[d] = {"type": "division", "color": DIVISION_COLOR}

        template_path = Path(template_path)
        env = Environment(loader=FileSystemLoader(str(template_path.parent)))
        template = env.get_template(template_path.name)

        return template.render(
            vis_js_cdn=_VIS_JS_CDN,
            title=title,
            nodes_json=json.dumps(nodes),
            edges_json=json.dumps(edges),
            adjacency_json=json.dumps(adjacency),
            node_meta_json=json.dumps(node_meta),
            divisions_json=json.dumps(divisions),
            category_colors=category_colors,
            categories=categories,
            staff_color=STAFF_COLOR,
            division_color=DIVISION_COLOR,
            dim_color=DIM_COLOR,
            glow_color=GLOW_COLOR,
            dot_size=DOT_SIZE,
            x_field=X_FIELD,
            x_staff=X_STAFF,
            x_division=X_DIVISION,
        )

    def network_bipartite(
        self,
        template_path: str | Path = "templates/network_bipartite.html",
        title: str = "DWR Division <-> Partner Organization Network",
    ) -> str:
        """
        Generate an interactive bipartite network graph:
            DWR Divisions <-> Partner Organizations

        Nodes sized by degree. Edge width = number of partnerships.
        Organizations colored by Organization Type.
        Force-directed layout that freezes after stabilization.

        :param template_path: Path to the Jinja2 HTML template
        :param title:         Chart title
        :return:              Rendered HTML string
        """
        from jinja2 import Environment, FileSystemLoader

        division_col = "DWR Division/ Office/ Branch"
        org_col = "Partnership Organization Name"
        org_type_col = "Organization Type"

        df = self.df[[division_col, org_col, org_type_col]].copy()
        df[division_col] = df[division_col].map(self._to_list_if_listlike)
        df[org_col] = df[org_col].map(self._to_list_if_listlike)
        df[org_type_col] = df[org_type_col].map(self._to_list_if_listlike)

        df = df.explode(division_col).explode(org_col).explode(org_type_col)
        df = df.dropna(subset=[division_col, org_col])
        df = df.apply(lambda col: col.str.strip() if col.dtype == "object" else col)

        edge_weights = df.groupby([division_col, org_col]).size().reset_index(name="weight")

        org_type_lookup = (
            df.dropna(subset=[org_type_col]).groupby(org_col)[org_type_col].first().to_dict()
        )

        divisions = sorted(df[division_col].unique().tolist())
        orgs = sorted(df[org_col].unique().tolist())

        DIVISION_PALETTE = [
            "#607D8B",
            "#546E7A",
            "#455A64",
            "#37474F",
            "#263238",
            "#78909C",
            "#90A4AE",
            "#B0BEC5",
            "#4DB6AC",
            "#26A69A",
            "#00897B",
            "#00796B",
            "#00695C",
            "#004D40",
        ]
        division_colors = {
            d: DIVISION_PALETTE[i % len(DIVISION_PALETTE)] for i, d in enumerate(divisions)
        }

        ORG_TYPE_PALETTE = {
            "University": "#1E88E5",
            "Federal agency or department": "#E53935",
            "State agency or department": "#43A047",
            "Public/Private": "#FB8C00",
            "Public Research Lab": "#8E24AA",
            "NGO": "#00ACC1",
            "Network/ Collaborative": "#F4511E",
            "Local or Regional agency": "#6D4C41",
            "Non-profit": "#D81B60",
            "Tribe": "#3949AB",
            "Other": "#90A4AE",
        }

        org_types_present = sorted(df[org_type_col].dropna().unique().tolist())
        org_type_colors: dict[str, str] = {}
        fallback_colors = ["#78909C", "#A1887F", "#4DD0E1", "#DCE775", "#FFD54F"]
        fi = 0
        for ot in org_types_present:
            if ot in ORG_TYPE_PALETTE:
                org_type_colors[ot] = ORG_TYPE_PALETTE[ot]
            else:
                org_type_colors[ot] = fallback_colors[fi % len(fallback_colors)]
                fi += 1

        DOT_SIZE = 14
        GLOW_COLOR = "#FFD700"
        DIM_COLOR = "#e8e8e8"

        nodes = []
        for d in divisions:
            nodes.append(
                {
                    "id": d,
                    "label": "",
                    "shape": "dot",
                    "color": {"background": division_colors[d], "border": division_colors[d]},
                    "font": {"size": 0},
                    "borderWidth": 0,
                    "group": "division",
                }
            )
        for org in orgs:
            org_type = org_type_lookup.get(org, "Other")
            org_color = org_type_colors.get(org_type, "#90A4AE")
            nodes.append(
                {
                    "id": org,
                    "label": "",
                    "shape": "square",
                    "color": {"background": org_color, "border": org_color},
                    "font": {"size": 0},
                    "borderWidth": 0,
                    "group": "org",
                }
            )

        max_weight = int(edge_weights["weight"].max())

        def scale_width(w: int) -> float:
            return 1 + (7 * (w - 1) / max(max_weight - 1, 1))

        edges = []
        edge_index: dict[str, dict] = {}

        for i, row in edge_weights.iterrows():
            div_id = row[division_col]
            org_id = row[org_col]
            weight = int(row["weight"])
            width = round(scale_width(weight), 2)
            edges.append(
                {
                    "id": f"e{i}",
                    "from": div_id,
                    "to": org_id,
                    "width": width,
                    "color": {"color": "rgba(160,160,160,0.5)"},
                }
            )
            edge_index[f"{div_id}|{org_id}"] = {"weight": weight}
            edge_index[f"{org_id}|{div_id}"] = {"weight": weight}

        all_ids = divisions + orgs
        adjacency: dict[str, list] = {n: [] for n in all_ids}
        for _, row in edge_weights.iterrows():
            d = row[division_col]
            o = row[org_col]
            adjacency[d].append(o)
            adjacency[o].append(d)
        adjacency = {k: list(set(v)) for k, v in adjacency.items()}

        node_meta: dict[str, dict] = {}
        for d in divisions:
            node_meta[d] = {"type": "division", "color": division_colors[d]}
        for org in orgs:
            org_type = org_type_lookup.get(org, "Other")
            org_color = org_type_colors.get(org_type, "#90A4AE")
            node_meta[org] = {"type": "org", "color": org_color, "orgType": org_type}

        template_path = Path(template_path)
        env = Environment(loader=FileSystemLoader(str(template_path.parent)))
        template = env.get_template(template_path.name)

        return template.render(
            vis_js_cdn=_VIS_JS_CDN,
            title=title,
            nodes_json=json.dumps(nodes),
            edges_json=json.dumps(edges),
            adjacency_json=json.dumps(adjacency),
            edge_index_json=json.dumps(edge_index),
            node_meta_json=json.dumps(node_meta),
            division_ids_json=json.dumps(divisions),
            org_type_colors=org_type_colors,
            org_type_colors_json=json.dumps(org_type_colors),
            glow_color=GLOW_COLOR,
            dim_color=DIM_COLOR,
            dot_size=DOT_SIZE,
        )

    def save_html(self, html: str, output_path: str | Path) -> Path:
        """
        Save an HTML string returned by a chart method to disk.

        :param html:        HTML string from e.g. network_tripartite()
        :param output_path: Destination file path
        :return:            Resolved Path to the saved file
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Saved to '{out}'")
        return out
