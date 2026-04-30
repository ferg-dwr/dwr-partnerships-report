"""
networks.py — vis.js network graph generators.

All functions accept a PartnershipData instance, render a Jinja2 HTML
template, and return the rendered HTML string.

vis-network is loaded from CDN — no local JS bundling required.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from dwr_report.ingest.loader import PartnershipData, to_list_if_listlike

# vis-network CDN reference injected into templates as {{ vis_js_cdn }}
_VIS_JS_CDN = "https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_CATEGORY_PALETTE = [
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

_DIVISION_PALETTE = [
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

_ORG_TYPE_PALETTE = {
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

_FALLBACK_COLORS = ["#78909C", "#A1887F", "#4DD0E1", "#DCE775", "#FFD54F"]


def _load_template(template_path: Path) -> Any:
    env = Environment(loader=FileSystemLoader(str(template_path.parent)))
    return env.get_template(template_path.name)


def network_tripartite(
    data: PartnershipData,
    template_path: str | Path = "templates/network_tripartite.html",
    title: str = "Science Field <-> Staff <-> Division Network",
) -> str:
    """
    Generate an interactive tripartite network graph.
    Requires enrich_science_fields() to have been called on `data` first.

    :param data:          PartnershipData instance (must be enriched)
    :param template_path: Path to the Jinja2 HTML template
    :param title:         Chart title
    :return:              Rendered HTML string
    """
    staff_col = "Main DWR Point of Contact"
    division_col = "DWR Division/ Office/ Branch"
    fields_col = "Science and Technology Fields"
    category_col = "1st Level Science Category"

    if category_col not in data.df.columns:
        raise ValueError(
            f"'{category_col}' column not found. "
            "Please run enrich_science_fields() before calling network_tripartite()."
        )

    df = data.df[[staff_col, division_col, fields_col, category_col]].copy()
    df[fields_col] = df[fields_col].map(to_list_if_listlike)
    df[category_col] = df[category_col].map(to_list_if_listlike)
    # division_col is a plain string in Microsoft Lists exports — no explosion needed

    df = df.explode(fields_col).explode(category_col)
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
    category_colors = {
        cat: _CATEGORY_PALETTE[i % len(_CATEGORY_PALETTE)] for i, cat in enumerate(categories)
    }

    fields_by_category: dict[str, list] = defaultdict(list)
    for field, cat in sorted(field_to_category.items()):
        fields_by_category[cat].append(field)
    for cat in fields_by_category:
        fields_by_category[cat].sort()

    divisions = sorted(df[division_col].unique().tolist())
    staff = sorted(df[staff_col].unique().tolist())

    CANVAS_HEIGHT = 4000
    X_FIELD, X_STAFF, X_DIVISION = -700, 0, 700
    PADDING, GROUP_GAP, DOT_SIZE = 60, 80, 14
    STAFF_COLOR = "#81C784"
    DIVISION_COLOR = "#FFB74D"
    DIM_COLOR = "#e8e8e8"
    GLOW_COLOR = "#FFD700"

    def spread_evenly(items: list) -> list[int]:
        n = len(items)
        if n == 1:
            return [CANVAS_HEIGHT // 2]
        step = (CANVAS_HEIGHT - 2 * PADDING) / (n - 1)
        return [int(PADDING + i * step) for i in range(n)]

    staff_positions = {s: y for s, y in zip(staff, spread_evenly(staff), strict=False)}
    division_positions = {d: y for d, y in zip(divisions, spread_evenly(divisions), strict=False)}

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

    template = _load_template(Path(template_path))
    return str(
        template.render(
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
    )


def network_bipartite(
    data: PartnershipData,
    template_path: str | Path = "templates/network_bipartite.html",
    title: str = "DWR Division <-> Partner Organization Network",
) -> str:
    """
    Generate an interactive bipartite network graph:
        DWR Divisions <-> Partner Organizations

    Nodes sized by degree. Edge width = number of partnerships.
    Organizations colored by Organization Type.
    Force-directed layout that freezes after stabilization.

    :param data:          PartnershipData instance
    :param template_path: Path to the Jinja2 HTML template
    :param title:         Chart title
    :return:              Rendered HTML string
    """
    division_col = "DWR Division/ Office/ Branch"
    org_col = "Partnership Organization Name"
    org_type_col = "Organization Type"

    df = data.df[[division_col, org_col, org_type_col]].copy()
    df[org_col] = df[org_col].map(to_list_if_listlike)
    df[org_type_col] = df[org_type_col].map(to_list_if_listlike)
    # division_col is a plain string in Microsoft Lists exports — no explosion needed

    df = df.explode(org_col).explode(org_type_col)
    df = df.dropna(subset=[division_col, org_col])
    df = df.apply(lambda col: col.str.strip() if col.dtype == "object" else col)

    edge_weights = df.groupby([division_col, org_col]).size().reset_index(name="weight")

    org_type_lookup = (
        df.dropna(subset=[org_type_col]).groupby(org_col)[org_type_col].first().to_dict()
    )

    divisions = sorted(df[division_col].unique().tolist())
    orgs = sorted(df[org_col].unique().tolist())

    division_colors = {
        d: _DIVISION_PALETTE[i % len(_DIVISION_PALETTE)] for i, d in enumerate(divisions)
    }

    org_types_present = sorted(df[org_type_col].dropna().unique().tolist())
    org_type_colors: dict[str, str] = {}
    fi = 0
    for ot in org_types_present:
        if ot in _ORG_TYPE_PALETTE:
            org_type_colors[ot] = _ORG_TYPE_PALETTE[ot]
        else:
            org_type_colors[ot] = _FALLBACK_COLORS[fi % len(_FALLBACK_COLORS)]
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

    # --- Top organizations summary (static, generated at report time) ---
    # Top partner orgs by number of DWR division connections
    org_degree = edge_weights.groupby(org_col)["weight"].sum().sort_values(ascending=False)
    top_orgs = [
        {"name": org, "connections": int(org_degree[org])} for org in org_degree.head(5).index
    ]

    # Top DWR divisions by number of partner organizations
    div_degree = edge_weights.groupby(division_col)["weight"].sum().sort_values(ascending=False)
    top_divisions = [
        {"name": div, "connections": int(div_degree[div])} for div in div_degree.head(5).index
    ]

    # --- Top organizations summary (static, generated at report time) ---
    org_degree = edge_weights.groupby(org_col)["weight"].sum().sort_values(ascending=False)
    top_orgs = [
        {"name": org, "connections": int(org_degree[org])} for org in org_degree.head(5).index
    ]

    div_degree = edge_weights.groupby(division_col)["weight"].sum().sort_values(ascending=False)
    top_divisions = [
        {"name": div, "connections": int(div_degree[div])} for div in div_degree.head(5).index
    ]

    template = _load_template(Path(template_path))
    return str(
        template.render(
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
            top_orgs_json=json.dumps(top_orgs),
            top_divisions_json=json.dumps(top_divisions),
        )
    )


def save_html(html: str, output_path: str | Path) -> Path:
    """
    Save a rendered HTML string to disk.

    :param html:        HTML string from e.g. network_tripartite()
    :param output_path: Destination file path
    :return:            Resolved Path to the saved file
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Saved to '{out}'")
    return out
