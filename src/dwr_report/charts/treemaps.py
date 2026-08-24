"""
treemaps.py — Treemap chart generators.

treemap()          — Plotly treemap for ad-hoc notebook use.
treemap_coverage() — Custom SVG treemap (squarified layout, React/Babel)
                     rendered from templates/treemap_coverage.html.
                     Returns a self-contained HTML string.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
from jinja2 import Environment, FileSystemLoader

from dwr_report import content
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
    return template.render(
        taxonomy_json=taxonomy_json,
        terms={
            "initiatives": content.TERM_INITIATIVES,
            "initiativesLower": content.TERM_INITIATIVES_LOWER,
            "fieldTags": content.TERM_FIELD_TAGS,
            "fieldTagsLower": content.TERM_FIELD_TAGS_LOWER,
        },
    )


# ---------------------------------------------------------------------------
# Server-side squarified treemap -> SVG (for PDF export)
#
# Ports the squarified layout, blue ramp, hatched gaps, and label fitting from
# templates/treemap_coverage.html so the treemap can be rendered to vector PDF
# without a browser. Returns the SVG plus per-cell tooltip regions.
# ---------------------------------------------------------------------------

_STOPS = [
    (0.0, "#EAF2FA"),
    (0.25, "#B8D3EC"),
    (0.5, "#6AA5D2"),
    (0.75, "#2F6FB0"),
    (1.0, "#0B3D75"),
]
_GAP_FILL, _GAP_TEXT, _GAP_HATCH = "#E5E5E2", "#7A7A75", "#D2D2CE"


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _ramp_color(t: float) -> str:
    t = max(0.0, min(1.0, t))
    for i in range(1, len(_STOPS)):
        if t <= _STOPS[i][0]:
            t0, c0 = _STOPS[i - 1]
            t1, c1 = _STOPS[i]
            k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            a, b = _hex_rgb(c0), _hex_rgb(c1)
            rgb = tuple(round(a[j] + (b[j] - a[j]) * k) for j in range(3))
            return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
    return _STOPS[-1][1]


def _text_on(hex_color: str) -> str:
    r, g, b = _hex_rgb(hex_color)
    return "#FFFFFF" if (0.2126 * r + 0.7152 * g + 0.0722 * b) < 140 else "#0B1F33"


def _squarify(items: list[dict], x: float, y: float, w: float, h: float) -> list[dict]:
    """Squarified treemap layout. Items have 'value' and 'datum'; returns placed rects."""
    result: list[dict] = []
    if not items:
        return result
    total = sum(i["value"] for i in items)
    if total <= 0:
        return result
    scale = (w * h) / total
    scaled = [{**i, "area": i["value"] * scale} for i in items]
    rect = {"x": x, "y": y, "w": w, "h": h}
    row: list[dict] = []

    def worst(candidate: list[dict], side: float) -> float:
        if not candidate:
            return float("inf")
        s = sum(r["area"] for r in candidate)
        mn = min(r["area"] for r in candidate)
        mx = max(r["area"] for r in candidate)
        s2, side2 = s * s, side * side
        return float(max((side2 * mx) / s2, s2 / (side2 * mn)))

    def layout_row(current: list[dict], rct: dict) -> dict:
        side = min(rct["w"], rct["h"])
        s = sum(r["area"] for r in current)
        other = s / side if side else 0.0
        cx, cy = rct["x"], rct["y"]
        if rct["w"] >= rct["h"]:
            for r in current:
                rh = r["area"] / other if other else 0.0
                result.append({"x": cx, "y": cy, "w": other, "h": rh, "datum": r["datum"]})
                cy += rh
            return {
                "x": rct["x"] + other,
                "y": rct["y"],
                "w": rct["w"] - other,
                "h": rct["h"],
            }
        for r in current:
            rw = r["area"] / other if other else 0.0
            result.append({"x": cx, "y": cy, "w": rw, "h": other, "datum": r["datum"]})
            cx += rw
        return {
            "x": rct["x"],
            "y": rct["y"] + other,
            "w": rct["w"],
            "h": rct["h"] - other,
        }

    i = 0
    while i < len(scaled):
        item = scaled[i]
        side = min(rect["w"], rect["h"])
        new_row = [*row, item]
        if not row or worst(new_row, side) <= worst(row, side):
            row = new_row
            i += 1
        else:
            rect = layout_row(row, rect)
            row = []
    if row:
        layout_row(row, rect)
    return result


def _fit_label(name: str, w: float, h: float, min_size: int = 9, max_size: int = 13) -> dict | None:
    pad = 7
    iw, ih = w - pad * 2, h - pad * 2
    if iw < 14 or ih < 14:
        return None
    words = name.split()
    for size in range(max_size, min_size - 1, -1):
        cw, lh = size * 0.6, size * 1.15
        lines: list[str] = []
        cur = ""
        for wd in words:
            test = f"{cur} {wd}" if cur else wd
            if len(test) * cw <= iw or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        if max((len(line) * cw for line in lines), default=0) <= iw and len(lines) * lh <= ih:
            return {"lines": lines, "size": size, "line_h": lh}
    return None


def _layout_treemap(taxonomy: list[dict], width: float, height: float) -> list[dict]:
    header_h, gap, inset = 28, 3, 6
    # Size cells by sqrt(count) so a few large fields don't crush the small ones
    # into unreadable slivers. Color still encodes the exact count (see max_count).
    sized = [math.sqrt(s["count"]) for c in taxonomy for s in c["subfields"] if s["count"] > 0]
    mean = sum(sized) / max(1, len(sized))
    gap_val = max(0.9, mean * 0.55)

    def cell_value(count: int) -> float:
        return math.sqrt(count) if count > 0 else gap_val

    cats = []
    for c in taxonomy:
        subs: list[dict[str, Any]] = sorted(
            (
                {
                    "value": cell_value(s["count"]),
                    "datum": {**s, "category": c["category"]},
                }
                for s in c["subfields"]
            ),
            key=lambda d: -d["value"],
        )
        cats.append(
            {
                "category": c["category"],
                "subs": subs,
                "total": sum(s["value"] for s in subs),
            }
        )

    cat_items = sorted(({"value": c["total"], "datum": c} for c in cats), key=lambda d: -d["value"])
    cat_rects = _squarify(cat_items, 0, 0, width, height)

    groups = []
    for r in cat_rects:
        cat = r["datum"]
        sub_rects = _squarify(
            cat["subs"],
            r["x"] + inset,
            r["y"] + header_h,
            max(0, r["w"] - inset * 2),
            max(0, r["h"] - header_h - inset),
        )
        cells = []
        for sr in sub_rects:
            gw = min(gap, sr["w"] * 0.6)  # never let the gap eat a tiny cell
            gh = min(gap, sr["h"] * 0.6)
            cells.append(
                {
                    "x": sr["x"] + gw / 2,
                    "y": sr["y"] + gh / 2,
                    "w": max(1.0, sr["w"] - gw),
                    "h": max(1.0, sr["h"] - gh),
                    "datum": sr["datum"],
                }
            )
        groups.append(
            {
                "frame": {"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]},
                "header": {
                    "x": r["x"],
                    "y": r["y"],
                    "w": r["w"],
                    "header_h": header_h,
                    "category": cat["category"],
                    "total": sum(
                        i["datum"]["count"] for i in cat["subs"] if i["datum"]["count"] > 0
                    ),
                    "gap_count": sum(1 for i in cat["subs"] if i["datum"]["count"] == 0),
                },
                "cells": cells,
            }
        )
    return groups


def treemap_coverage_svg(
    data: PartnershipData,
    taxonomy_path: str | Path,
    width: float = 920,
    height: float | None = None,
) -> tuple[str, list[tuple[float, float, float, float, str]]]:
    """Render the coverage treemap as a standalone SVG string plus tooltip regions.

    Returns (svg, regions) where each region is (x, y, w, h, tooltip_text).
    Mirrors the browser treemap: blue ramp by partnership count, grey hatched gaps.
    When ``height`` is not given it grows with the number of subfields so dense,
    skewed data doesn't squeeze the smallest cells out of existence.
    """
    taxonomy = _build_taxonomy_json(data, taxonomy_path)
    all_counts = [s["count"] for c in taxonomy for s in c["subfields"]]
    total_part = sum(all_counts)
    total_subs = len(all_counts)
    gaps = sum(1 for c in all_counts if c == 0)
    max_count = max([*all_counts, 0])
    max_cat_total = max([sum(s["count"] for s in c["subfields"]) for c in taxonomy] + [0])

    summary_h = 88.0
    if height is None:
        # Area calibrated to keep the smallest cells visible, divided by the
        # actual width — so a wide (landscape) canvas stays landscape-proportioned
        # instead of growing into a very tall page.
        tree_area = max(560.0, total_subs * 30.0) * 920.0
        height = summary_h + tree_area / width
    groups = _layout_treemap(taxonomy, width, max(0.0, height - summary_h))

    m = 20.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{-m:.0f} {-m:.0f} {width + 2 * m:.0f} {height + 2 * m:.0f}" '
        f'width="{width + 2 * m:.0f}" height="{height + 2 * m:.0f}" '
        f'font-family="Public Sans, Arial, sans-serif">',
        f'<rect x="{-m:.0f}" y="{-m:.0f}" width="{width + 2 * m:.0f}" '
        f'height="{height + 2 * m:.0f}" fill="#FFFFFF"/>',
        "<defs>"
        '<pattern id="hatch" patternUnits="userSpaceOnUse" width="6" height="6" '
        f'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="{_GAP_HATCH}" '
        'stroke-width="1.6"/></pattern>'
        '<linearGradient id="tmramp" x1="0" y1="0" x2="1" y2="0">'
        + "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in _STOPS)
        + "</linearGradient></defs>",
    ]

    # Summary band: stat cells + gradient/gap legend
    covered_cats = sum(1 for c in taxonomy if any(s["count"] > 0 for s in c["subfields"]))
    for i, (stat_label, stat_value, stat_color) in enumerate(
        [
            (content.TERM_FIELD_TAGS.upper(), str(total_part), "#003366"),
            ("SCIENCE AREAS COVERED", f"{covered_cats}/{len(taxonomy)}", "#003366"),
            ("SUBFIELDS COVERED", f"{total_subs - gaps}/{total_subs}", "#003366"),
            ("COVERAGE GAPS", str(gaps), "#B85A1E"),
        ]
    ):
        cx = 4 + i * 200
        parts.append(
            f'<text x="{cx}" y="30" font-family="monospace" font-size="22" font-weight="700" '
            f'fill="{stat_color}">{stat_value}</text>'
            f'<text x="{cx}" y="46" font-size="9.5" fill="#888" '
            f'letter-spacing="0.06em">{stat_label}</text>'
        )
    parts.append(
        f'<text x="4" y="76" font-size="10" fill="#666">'
        f"{escape(content.TERM_INITIATIVES)}</text>"
        '<rect x="132" y="66" width="120" height="12" rx="2" fill="url(#tmramp)"/>'
        '<text x="258" y="76" font-size="9" fill="#999">fewer \u2192 more</text>'
        f'<rect x="348" y="66" width="14" height="12" rx="2" fill="{_GAP_FILL}"/>'
        '<rect x="348" y="66" width="14" height="12" rx="2" fill="url(#hatch)"/>'
        f'<text x="368" y="76" font-size="10" fill="#666">Coverage gap '
        f"(0 {escape(content.TERM_INITIATIVES_LOWER)})</text>"
    )

    parts.append(f'<g transform="translate(0,{summary_h:.0f})">')
    regions: list[tuple[float, float, float, float, str]] = []

    for g in groups:
        fr = g["frame"]
        hd = g["header"]
        norm = hd["total"] / max_cat_total if max_cat_total > 0 else 0.0
        hfill = _ramp_color(0.55 + 0.45 * norm)
        # Parent frame — the tint that visually encloses this category's cells
        parts.append(
            f'<rect x="{fr["x"]:.1f}" y="{fr["y"]:.1f}" width="{max(0, fr["w"]):.1f}" '
            f'height="{max(0, fr["h"]):.1f}" fill="{hfill}" rx="3"/>'
        )
        pad = 10
        title_size = 11.5
        max_title_w = hd["w"] - pad * 2
        if len(hd["category"]) * (title_size * 0.62) > max_title_w:
            title_size = max(8.0, max_title_w / (len(hd["category"]) * 0.62 or 1))
        title_y = hd["y"] + hd["header_h"] * 0.38 + title_size * 0.35
        # hd["total"] sums this category's subfield counts, so an initiative tagged
        # with two subfields in the same category is counted twice — these are field
        # tags, not distinct initiatives.
        meta = f"{hd['total']} field tag{'s' if hd['total'] != 1 else ''}"
        if hd["gap_count"] > 0:
            meta += f" \u00b7 {hd['gap_count']} gap{'s' if hd['gap_count'] != 1 else ''}"
        meta_y = hd["y"] + hd["header_h"] * 0.72 + 3
        clip = f"hdr{int(hd['x'])}_{int(hd['y'])}"
        parts.append(
            f'<clipPath id="{clip}"><rect x="{hd["x"]:.1f}" y="{hd["y"]:.1f}" '
            f'width="{max(0, hd["w"]):.1f}" height="{hd["header_h"]}"/></clipPath>'
            f'<g clip-path="url(#{clip})">'
            f'<text x="{hd["x"] + pad:.1f}" y="{title_y:.1f}" fill="#FFFFFF" '
            f'font-size="{title_size:.1f}" font-weight="700">{escape(hd["category"])}</text>'
            f'<text x="{hd["x"] + pad:.1f}" y="{meta_y:.1f}" fill="#FFFFFF" fill-opacity="0.65" '
            f'font-family="monospace" font-size="9.5">{escape(meta)}</text></g>'
        )

        for cell in g["cells"]:
            d = cell["datum"]
            is_gap = d["count"] == 0
            t = (d["count"] / max_count) if (max_count > 0 and not is_gap) else -1.0
            fill = _GAP_FILL if is_gap else _ramp_color(t)
            fg = _GAP_TEXT if is_gap else _text_on(fill)
            x, y, w, h = cell["x"], cell["y"], cell["w"], cell["h"]
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'fill="{fill}" stroke="white" stroke-width="1" rx="2"/>'
            )
            if is_gap:
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                    f'fill="url(#hatch)" rx="2"/>'
                )
            label = _fit_label(
                d["name"], w, h, **({"max_size": 12, "min_size": 7} if is_gap else {})
            )
            rotated = False
            if label is None:
                # Tall, narrow cell: try the label vertically (swap width/height)
                rl = _fit_label(d["name"], h, w, max_size=11, min_size=7)
                if rl is not None:
                    label, rotated = rl, True
            if label is None and w >= 20 and h >= 12:
                # Last resort: truncate to one small horizontal line
                max_chars = max(2, int((w - 8) / (8 * 0.6)))
                nm = d["name"]
                trunc = nm if len(nm) <= max_chars else nm[: max_chars - 1] + "\u2026"
                label = {"lines": [trunc], "size": 8, "line_h": 8 * 1.15}
            if label:
                cclip = f"c{int(x)}_{int(y)}"
                weight = 500 if is_gap else 600
                lines = label["lines"]
                count_txt = ""
                if rotated:
                    cxc, cyc, n = x + w / 2, y + h / 2, len(lines)
                    tspans = "".join(
                        f'<tspan x="{cxc:.1f}" '
                        f'dy="{(-(n - 1) * label["line_h"] / 2) if i == 0 else label["line_h"]:.1f}">'
                        f"{escape(line)}</tspan>"
                        for i, line in enumerate(lines)
                    )
                    text_el = (
                        f'<text x="{cxc:.1f}" y="{cyc:.1f}" fill="{fg}" text-anchor="middle" '
                        f'transform="rotate(-90 {cxc:.1f} {cyc:.1f})" '
                        f'font-size="{label["size"]}" font-weight="{weight}">{tspans}</text>'
                    )
                else:
                    ly = y + 7 + label["size"] * 0.85
                    tspans = "".join(
                        f'<tspan x="{x + 7:.1f}" dy="{0 if i == 0 else label["line_h"]:.1f}">'
                        f"{escape(line)}</tspan>"
                        for i, line in enumerate(lines)
                    )
                    text_el = (
                        f'<text x="{x + 7:.1f}" y="{ly:.1f}" fill="{fg}" '
                        f'font-size="{label["size"]}" font-weight="{weight}">{tspans}</text>'
                    )
                    if not is_gap and w >= 60 and h >= 36 and len(lines) <= 3:
                        count_txt = (
                            f'<text x="{x + 7:.1f}" y="{y + h - 7:.1f}" fill="{fg}" fill-opacity="0.75" '
                            f'font-family="monospace" font-size="10">{d["count"]}</text>'
                        )
                # Clip label + count to the cell so text can never spill outside its box
                parts.append(
                    f'<clipPath id="{cclip}"><rect x="{x:.1f}" y="{y:.1f}" '
                    f'width="{w:.1f}" height="{h:.1f}"/></clipPath>'
                    f'<g clip-path="url(#{cclip})">{text_el}{count_txt}</g>'
                )
            if w >= 6 and h >= 6:
                # A subfield's count is the number of distinct initiatives tagged
                # with it, so "initiatives" is the correct noun at the cell level.
                tip = (
                    f"{d['name']}: coverage gap (0 {content.TERM_INITIATIVES_LOWER})"
                    if is_gap
                    else f"{d['name']}: {content.plural_initiatives(d['count'])}"
                )
                regions.append((x, y + summary_h, w, h, tip))

    parts.append("</g></svg>")
    return "".join(parts), regions
