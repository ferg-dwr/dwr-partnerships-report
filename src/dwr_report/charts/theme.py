"""
theme.py — Shared visual theme for chart modules.

Single source of truth for brand colors, fonts, and the organization-type
palette, so the summary dashboard and the network graphs stay visually
consistent. Colors match the DWR PowerBI dashboard scheme.
"""

from __future__ import annotations

# Brand + neutral colors
BRAND = "#1F3A47"  # dark slate-navy: bars, stat numbers, primary accents
TEXT = "#333333"
MUTED = "#888888"
GRID = "#E6E6E6"
CARD_BORDER = "#E2E2E2"

FONT = "Public Sans, Arial, Helvetica, sans-serif"

# Organization-type categorical palette (PowerBI dashboard scheme)
ORG_TYPE_COLORS: dict[str, str] = {
    "University": "#1F3A47",
    "Federal agency or department": "#5F8C9D",
    "Public/Private": "#9BCDD3",
    "State agency or department": "#3E6B3E",
    "NGO": "#B5901C",
    "Public Research Lab": "#E6A900",
    "Network/ Collaborative": "#EED27A",
    "Local or Regional agency": "#BDAF90",
    "Other": "#7EC3DB",
    "Non-profit": "#9C7A1E",
    "Tribe": "#FDB913",
}
ORG_TYPE_FALLBACK: list[str] = ["#8FA9B3", "#C2D4DA", "#6E8B6E", "#D9C68A", "#A9B7BD"]


def org_type_color(name: str, idx: int = 0) -> str:
    """Color for an organization type, falling back by index for unknown types."""
    return ORG_TYPE_COLORS.get(name, ORG_TYPE_FALLBACK[idx % len(ORG_TYPE_FALLBACK)])
