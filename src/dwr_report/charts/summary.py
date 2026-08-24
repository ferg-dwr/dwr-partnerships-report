"""
summary.py — Summary dashboard charts (recreating the public PowerBI view).

Recreates the DWR PowerBI summary view as a single self-contained SVG dashboard:
  - Two headline stat cards (total partnerships, total financial investment)
  - Partnering Organization Type (donut)
  - Investment Type (vertical bars)
  - Science Fields (horizontal bars, top N)
  - Partnership Activity (horizontal bars)

Follows the treemaps.py / networks.py convention: Python prepares the data and
geometry, then renders templates/summary_dashboard.html and returns the HTML
string. No external charting library — hand-built SVG. Colors match the DWR
PowerBI palette.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from dwr_report import content
from dwr_report.charts.theme import (
    BRAND,
    CARD_BORDER,
    FONT,
    GRID,
    MUTED,
    TEXT,
    org_type_color,
)
from dwr_report.ingest.loader import PartnershipData

SUMMARY_TEMPLATE = Path("templates/summary_dashboard.html")

# Columns driving each chart
_ORG_TYPE_COL = "Organization Type"
_INVESTMENT_COL = "DWR Investments"
_FIELDS_COL = "Science and Technology Fields"
_ACTIVITY_COL = "Partnership Type"
_AMOUNT_COLS = ["Total Contract Amount v2", "Total Contract Amount"]

# Canvas
_VB_W = 920
_VB_H = 690
_MARGIN = 20  # uniform breathing room around the dashboard content


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _explode_counts(data: PartnershipData, col: str) -> list[tuple[str, int]]:
    """Counts per value for a list-like column, using the loader's explode logic."""
    if col not in data.df.columns:
        return []
    exploded = data.prepare_plot_df([col])[col].astype(str).str.strip()
    counts = exploded[exploded != ""].value_counts()
    return [(str(k), int(v)) for k, v in counts.items()]


def _parse_amount(val: object) -> float:
    """Pull a numeric dollar amount out of a messy string cell."""
    if val is None:
        return 0.0
    digits = re.sub(r"[^0-9.]", "", str(val))
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def compute_summary(data: PartnershipData, top_n: int = 13) -> dict:
    """Compute all aggregates needed for the summary dashboard."""
    total_investment = 0.0
    for col in _AMOUNT_COLS:
        if col in data.df.columns:
            total_investment = float(data.df[col].map(_parse_amount).sum())
            if total_investment > 0:
                break

    return {
        "total_partnerships": len(data.df),
        "total_investment": total_investment,
        "org_types": _explode_counts(data, _ORG_TYPE_COL),
        "investment_types": _explode_counts(data, _INVESTMENT_COL),
        "science_fields": _explode_counts(data, _FIELDS_COL)[:top_n],
        "activities": _explode_counts(data, _ACTIVITY_COL)[:top_n],
    }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _fmt_money(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


def _annulus_path(cx: float, cy: float, r_out: float, r_in: float, a0: float, a1: float) -> str:
    """SVG path for a donut segment between angles a0..a1 (radians, clockwise from top)."""

    def pt(r: float, a: float) -> tuple[float, float]:
        return (cx + r * math.sin(a), cy - r * math.cos(a))

    # A full 360 sweep can't be drawn as one arc (start == end renders nothing),
    # so draw the ring as concentric circles and rely on fill-rule="evenodd".
    if (a1 - a0) >= 2 * math.pi - 1e-9:
        return (
            f"M{cx - r_out:.2f},{cy:.2f} "
            f"A{r_out:.2f},{r_out:.2f} 0 1 0 {cx + r_out:.2f},{cy:.2f} "
            f"A{r_out:.2f},{r_out:.2f} 0 1 0 {cx - r_out:.2f},{cy:.2f} Z "
            f"M{cx - r_in:.2f},{cy:.2f} "
            f"A{r_in:.2f},{r_in:.2f} 0 1 0 {cx + r_in:.2f},{cy:.2f} "
            f"A{r_in:.2f},{r_in:.2f} 0 1 0 {cx - r_in:.2f},{cy:.2f} Z"
        )

    large = 1 if (a1 - a0) > math.pi else 0
    x0o, y0o = pt(r_out, a0)
    x1o, y1o = pt(r_out, a1)
    x1i, y1i = pt(r_in, a1)
    x0i, y0i = pt(r_in, a0)
    return (
        f"M{x0o:.2f},{y0o:.2f} "
        f"A{r_out:.2f},{r_out:.2f} 0 {large} 1 {x1o:.2f},{y1o:.2f} "
        f"L{x1i:.2f},{y1i:.2f} "
        f"A{r_in:.2f},{r_in:.2f} 0 {large} 0 {x0i:.2f},{y0i:.2f} Z"
    )


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "\u2026"


def _build_donut(summary: dict) -> dict:
    px, py = 0, 120
    cx, cy, r_out, r_in = px + 95, py + 130, 78, 44
    items = summary["org_types"]
    total = sum(c for _, c in items) or 1

    segments, legend = [], []
    a = 0.0
    lx, ly = px + 195, py + 40
    for idx, (name, count) in enumerate(items):
        color = org_type_color(name, idx)
        a1 = a + (count / total) * 2 * math.pi
        segments.append({"d": _annulus_path(cx, cy, r_out, r_in, a, a1), "color": color})
        a = a1
        row_y = ly + idx * 17
        legend.append(
            {
                "color": color,
                "sx": lx,
                "sy": row_y - 8,
                "tx": lx + 15,
                "ty": row_y,
                "vx": lx + 200,
                "label": _truncate(name, 22),
                "value": f"{count} ({count / total * 100:.1f}%)",
            }
        )
    return {"segments": segments, "legend": legend}


def _build_vbars(summary: dict) -> dict:
    px, py, w, h = 475, 120, 445, 250
    plot_top, plot_bottom = py + 25, py + h - 40
    plot_h = plot_bottom - plot_top
    items = summary["investment_types"]
    max_v = max((c for _, c in items), default=1) or 1
    n = max(len(items), 1)
    slot = min(110, (w - 80) / n)
    bar_w = slot * 0.55
    x0 = px + 55

    bars = []
    for i, (name, count) in enumerate(items):
        bh = plot_h * count / max_v
        bx = x0 + i * slot + (slot - bar_w) / 2
        by = plot_bottom - bh
        words = name.split()
        if len(name) > 12 and len(words) > 1:
            mid = len(words) // 2
            labels = [
                {"text": " ".join(words[:mid]), "y": plot_bottom + 15},
                {"text": " ".join(words[mid:]), "y": plot_bottom + 27},
            ]
        else:
            labels = [{"text": name, "y": plot_bottom + 15}]
        bars.append(
            {
                "x": round(bx, 1),
                "y": round(by, 1),
                "w": round(bar_w, 1),
                "h": round(bh, 1),
                "cx": round(bx + bar_w / 2, 1),
                "vy": round(by - 5, 1),
                "value": count,
                "labels": labels,
            }
        )
    return {
        "baseline": {"x1": x0, "x2": px + w - 10, "y": plot_bottom},
        "bars": bars,
    }


def _build_hbar_panel(
    items: list[tuple[str, int]], px: float, py: float, w: float, h: float
) -> dict:
    plot_top = py + 18
    label_w = 150
    x0 = px + label_w
    bar_max_w = w - label_w - 35
    max_v = max((c for _, c in items), default=1) or 1
    n = max(len(items), 1)
    row_h = min(20, (h - 30) / n)
    bar_h = row_h * 0.62

    rows = []
    for i, (name, count) in enumerate(items):
        ry = plot_top + i * row_h
        bw = bar_max_w * count / max_v
        rows.append(
            {
                "label": _truncate(name, 24),
                "lx": px + label_w - 6,
                "ty": round(ry + bar_h - 1, 1),
                "bx": x0,
                "by": round(ry, 1),
                "bw": round(bw, 1),
                "bh": round(bar_h, 1),
                "vx": round(x0 + bw + 5, 1),
                "value": count,
            }
        )
    return {"rows": rows}


def _build_context(summary: dict) -> dict:
    money = _fmt_money(summary["total_investment"]) if summary["total_investment"] > 0 else "\u2014"
    card_x = (_VB_W - 360) // 2  # center the stat card in the canvas
    return {
        "vb_w": _VB_W,
        "vb_h": _VB_H,
        "vb": {
            "x": -_MARGIN,
            "y": -_MARGIN,
            "w": _VB_W + 2 * _MARGIN,
            "h": _VB_H + 2 * _MARGIN,
        },
        "font": FONT,
        "colors": {
            "brand": BRAND,
            "text": TEXT,
            "muted": MUTED,
            "grid": GRID,
            "card_border": CARD_BORDER,
        },
        "titles": [
            {"x": 222, "y": 120, "text": "Partnering Organization Type"},
            {"x": 697, "y": 120, "text": "Investment Type"},
            {"x": 222, "y": 400, "text": "Science Fields"},
            {"x": 697, "y": 400, "text": "Partnership Activity"},
        ],
        "stats": {
            "card": {"x": card_x, "y": 0, "w": 360, "h": 78},
            "p_x": card_x + 90,
            "m_x": card_x + 270,
            "num_y": 38,
            "lbl_y": 58,
            "partnerships": summary["total_partnerships"],
            "partnerships_label": content.TERM_INITIATIVES,
            "money": money,
        },
        "donut": _build_donut(summary),
        "vbars": _build_vbars(summary),
        "hbar_panels": [
            _build_hbar_panel(summary["science_fields"], 0, 400, 445, 280),
            _build_hbar_panel(summary["activities"], 475, 400, 445, 280),
        ],
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_summary(summary: dict, template_path: Path = SUMMARY_TEMPLATE) -> str:
    """Render the dashboard from a precomputed summary dict."""
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,
    )
    template = env.get_template(template_path.name)
    return template.render(**_build_context(summary))


def summary_dashboard(
    data: PartnershipData,
    template_path: Path = SUMMARY_TEMPLATE,
    top_n: int = 13,
) -> str:
    """Compute aggregates and render the summary dashboard as an HTML string."""
    return render_summary(compute_summary(data, top_n=top_n), template_path=template_path)
