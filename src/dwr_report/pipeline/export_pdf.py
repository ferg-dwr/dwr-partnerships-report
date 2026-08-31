"""
export_pdf.py — Export the external report as a vector PDF with hover tooltips.

Page 1: the summary dashboard. Page 2: the science-coverage treemap. Both are
generated as SVG (so every element's box is known), rendered to vector PDF
(crisp, selectable text), then overlaid with invisible form-field widgets whose
tooltip text (/TU) shows on hover in Adobe Acrobat Reader. Viewers without
form-tooltip support (Chrome, most mobile apps) still display the PDF fully;
only the hover text is unavailable — hence the note printed on each page.

Coordinate mapping is driven by each figure's own viewBox, so it stays correct
regardless of the figure's margin/origin.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from html import escape
from pathlib import Path

import cairosvg
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from dwr_report import content
from dwr_report.charts.summary import _build_context, compute_summary, render_summary
from dwr_report.charts.theme import FONT
from dwr_report.charts.treemaps import treemap_coverage_svg
from dwr_report.ingest.loader import PartnershipData

# Uniform page canvas: US Letter landscape at 96dpi-ish SVG units.
_PAGE_W, _PAGE_H = 1100.0, 850.0
_PAGE_MARGIN = 26.0  # keeps figures off the trim edge
_NOTE_H = 34  # top band height (SVG units) reserved for the note
_NOTE = (
    "NOTE: Open this PDF in Adobe Acrobat Reader to see the interactive "
    "hover tooltips on each figure."
)

Region = tuple[float, float, float, float, str]
_VIEWBOX_RE = re.compile(r'viewBox="\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"')


def _dashboard_regions(summary: dict, ctx: dict) -> list[Region]:
    """(x, y, w, h, tooltip) hotspots on the dashboard, in SVG content coordinates."""
    card_x = ctx["stats"]["card"]["x"]
    regions: list[Region] = [
        (
            card_x,
            0,
            180,
            78,
            f"{content.TERM_INITIATIVES}: {summary['total_partnerships']}",
        ),
        (card_x + 180, 0, 180, 78, f"Financial investment: {ctx['stats']['money']}"),
    ]
    for (name, _), leg in zip(summary["org_types"], ctx["donut"]["legend"], strict=True):
        regions.append((leg["sx"] - 2, leg["ty"] - 11, 230, 16, f"{name}: {leg['value']}"))
    for (name, count), bar in zip(summary["investment_types"], ctx["vbars"]["bars"], strict=True):
        regions.append((bar["x"], bar["y"], bar["w"], bar["h"], f"{name}: {count}"))
    for px, items, panel in (
        (0, summary["science_fields"], ctx["hbar_panels"][0]),
        (475, summary["activities"], ctx["hbar_panels"][1]),
    ):
        for (name, count), row in zip(items, panel["rows"], strict=True):
            regions.append((px, row["by"] - 2, 410, 16, f"{name}: {count}"))
    return regions


def _wrap_text(text: str, max_width: float, font_size: float, cw: float = 0.54) -> list[str]:
    """Greedy word-wrap: split text into lines that fit max_width at font_size."""
    max_chars = max(1, int(max_width / (font_size * cw)))
    lines: list[str] = []
    cur = ""
    for word in text.split():
        test = f"{cur} {word}" if cur else word
        if len(test) <= max_chars or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _intro_svg(width: float = 920, generated_at: str | None = None) -> str:
    """Title + Background-and-Purpose intro page (no tooltips)."""
    pad, tw = 44, width - 88
    stamp = generated_at or datetime.now().strftime("%B %-d, %Y")
    parts: list[str] = [
        f'<text x="{pad}" y="74" font-size="13" fill="#5F8C9D" font-weight="700" '
        f'letter-spacing="0.08em">{escape(content.REPORT_ORG.upper())}</text>',
        f'<text x="{width - pad:.0f}" y="74" font-size="11" fill="#7A8B93" '
        f'text-anchor="end">Last updated on {escape(stamp)}</text>',
    ]
    y = 120
    for line in _wrap_text(content.REPORT_TITLE, tw, 27, 0.6):
        parts.append(
            f'<text x="{pad}" y="{y}" font-size="27" fill="#1F3A47" '
            f'font-weight="700">{escape(line)}</text>'
        )
        y += 36
    y += 26
    parts.append(
        f'<text x="{pad}" y="{y}" font-size="16" fill="#1F3A47" '
        f'font-weight="700">{escape(content.INTRO_HEADING)}</text>'
    )
    y += 28
    contact = f"{content.CONTACT_PREFIX} {content.CONTACT_EMAIL}."
    for para in [*content.INTRO_PARAGRAPHS, contact]:
        for line in _wrap_text(para, tw, 12.5, 0.52):
            parts.append(
                f'<text x="{pad}" y="{y}" font-size="12.5" fill="#333">{escape(line)}</text>'
            )
            y += 20
        y += 14
    # The Acrobat tooltip note lives here, once, rather than repeating as a
    # band above every figure page.
    y += 6
    parts.append(
        f'<text x="{pad}" y="{y}" font-size="11.5" font-style="italic" '
        f'fill="#5F8C9D">{_NOTE}</text>'
    )
    total_h = y + 24
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {total_h:.0f}" '
        f'width="{width:.0f}" height="{total_h:.0f}" font-family="{FONT}">'
        f'<rect width="{width:.0f}" height="{total_h:.0f}" fill="#FFFFFF"/>'
        f"{''.join(parts)}</svg>"
    )


def _dashboard_with_captions(dash_svg: str) -> str:
    """Append the investment explanation + disclaimer below the dashboard figure."""
    match = _VIEWBOX_RE.search(dash_svg)
    if match is None:
        return dash_svg
    vx, vy, vw, vh = (float(v) for v in match.groups())
    body = dash_svg[dash_svg.index(">") + 1 : dash_svg.rindex("</svg>")]
    parts: list[str] = []
    y = vy + vh + 2
    for line in _wrap_text(content.INVESTMENT_NOTE, 900, 11, 0.52):
        parts.append(f'<text x="0" y="{y:.0f}" font-size="11" fill="#333">{escape(line)}</text>')
        y += 14
    y += 6
    for line in _wrap_text(f"* {content.FINANCIAL_DISCLAIMER}", 900, 10, 0.52):
        parts.append(f'<text x="0" y="{y:.0f}" font-size="10" fill="#777">{escape(line)}</text>')
        y += 13
    # Breathing room below the last line so the disclaimer is not flush against
    # the trim edge once the figure is letterboxed onto the page canvas.
    new_vh = (y + 26) - vy
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.0f} {vy:.0f} {vw:.0f} {new_vh:.0f}" '
        f'width="{vw:.0f}" height="{new_vh:.0f}" font-family="{FONT}">'
        f'<rect x="{vx:.0f}" y="{vy:.0f}" width="{vw:.0f}" height="{new_vh:.0f}" fill="#FFFFFF"/>'
        f"{body}{''.join(parts)}</svg>"
    )


def _treemap_with_header(tree_svg: str) -> tuple[str, float, list[Region]]:
    """Prepend the treemap's title, description, counting note, and how-to-read list.

    The block is added by extending the figure's viewBox upward, so the treemap's
    own content coordinates are unchanged. Returns (svg, y_shift, link_regions),
    where ``y_shift`` is how far the original content moved down (existing tooltip
    regions must be offset by it) and ``link_regions`` are hotspots for the
    taxonomy-definitions URL.
    """
    match = _VIEWBOX_RE.search(tree_svg)
    if match is None:
        raise ValueError("SVG has no viewBox")
    vx, vy, vw, vh = (float(v) for v in match.groups())
    body = tree_svg[tree_svg.index(">") + 1 : tree_svg.rindex("</svg>")]
    tw = vw - 8

    parts: list[str] = []
    links: list[Region] = []
    # Leave room for the 19pt title's ascender above its baseline.
    y = 22.0

    parts.append(
        f'<text x="4" y="{y:.0f}" font-size="19" font-weight="700" fill="#1F3A47">'
        f"{escape(content.TREEMAP_TITLE)}</text>"
    )
    y += 30
    for para in (content.TREEMAP_DESCRIPTION, content.TREEMAP_COUNTING_NOTE):
        for line in _wrap_text(para, tw, 11.5, 0.52):
            parts.append(
                f'<text x="4" y="{y:.0f}" font-size="11.5" fill="#333">{escape(line)}</text>'
            )
            y += 17
        y += 8

    # Taxonomy definitions link — drawn as text, made clickable by a /Link annot.
    link_label = content.TAXONOMY_LINK_TEXT
    lw = len(link_label) * 5.7
    parts.append(
        f'<text x="4" y="{y:.0f}" font-size="11" fill="#1456A0">{escape(link_label)}</text>'
        f'<rect x="4" y="{y + 2:.0f}" width="{lw:.0f}" height="0.7" fill="#1456A0"/>'
    )
    links.append((4, y - 11, lw, 15, content.TAXONOMY_URL))
    y += 20

    parts.append(
        f'<text x="4" y="{y:.0f}" font-size="11.5" font-weight="700" fill="#1F3A47">'
        "How to read this figure</text>"
    )
    y += 17
    for item in content.TREEMAP_HOW_TO_READ:
        wrapped = _wrap_text(item, tw - 16, 11, 0.52)
        for i, line in enumerate(wrapped):
            bullet = "\u2022 " if i == 0 else "  "
            parts.append(
                f'<text x="{4 if i == 0 else 14}" y="{y:.0f}" font-size="11" fill="#333">'
                f"{escape(bullet + line) if i == 0 else escape(line)}</text>"
            )
            y += 14
        y += 2
    y += 10

    shift = y - vy
    shifted_links = [(lx, ly + vy, lw, lh, url) for lx, ly, lw, lh, url in links]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vx:.0f} {vy:.0f} {vw:.0f} {vh + shift:.0f}" '
        f'width="{vw:.0f}" height="{vh + shift:.0f}" font-family="{FONT}">'
        f'<rect x="{vx:.0f}" y="{vy:.0f}" width="{vw:.0f}" height="{vh + shift:.0f}" fill="#FFFFFF"/>'
        f'<g transform="translate(0,{vy:.0f})">{"".join(parts)}</g>'
        f'<g transform="translate(0,{shift:.0f})">{body}</g>'
        f"</svg>"
    )
    return svg, shift, shifted_links


def _wrap_with_note(inner_svg: str) -> tuple[str, float, float, float, float]:
    """Add an italic note band above a figure by extending its viewBox upward.

    Content coordinates are unchanged. Returns (wrapped_svg, vx, vy, vw, vh) for
    the page's viewBox so annotations can be mapped correctly.
    """
    match = _VIEWBOX_RE.search(inner_svg)
    if match is None:
        raise ValueError("SVG has no viewBox")
    vx, vy, vw, vh = (float(v) for v in match.groups())
    body = inner_svg[inner_svg.index(">") + 1 : inner_svg.rindex("</svg>")]
    new_vy, new_vh = vy - _NOTE_H, vh + _NOTE_H
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vx:.0f} {new_vy:.0f} {vw:.0f} {new_vh:.0f}" '
        f'width="{vw:.0f}" height="{new_vh:.0f}" font-family="{FONT}">'
    )
    note = (
        f'<rect x="{vx:.0f}" y="{new_vy:.0f}" width="{vw:.0f}" height="{new_vh:.0f}" fill="#FFFFFF"/>'
        f'<text x="{vx + 24:.0f}" y="{new_vy + 23:.0f}" font-size="13" font-style="italic" '
        f'fill="#555">{_NOTE}</text>'
    )
    return f"{head}{note}{body}</svg>", vx, new_vy, vw, new_vh


def _add_page(
    writer: PdfWriter,
    all_fields: ArrayObject,
    inner_svg: str,
    regions: list[Region],
    with_note: bool = True,
    links: list[Region] | None = None,
) -> None:
    """Render one SVG figure to a PDF page and overlay its tooltip annotations."""
    if with_note:
        wrapped, vx, vy, vw, vh = _wrap_with_note(inner_svg)
    else:
        match = _VIEWBOX_RE.search(inner_svg)
        if match is None:
            raise ValueError("SVG has no viewBox")
        vx, vy, vw, vh = (float(v) for v in match.groups())
        wrapped = inner_svg
    # Every page is rendered onto the same canvas (US Letter landscape) so the
    # exported PDF has uniform page dimensions. The figure is scaled to fit
    # while preserving its aspect ratio, then centred; the leftover margin is
    # white. Without this, page sizes track each figure's natural size and the
    # PDF pages come out visibly different shapes.
    avail_w, avail_h = _PAGE_W - 2 * _PAGE_MARGIN, _PAGE_H - 2 * _PAGE_MARGIN
    scale = min(avail_w / vw, avail_h / vh)
    dw, dh = vw * scale, vh * scale
    ox, oy = (_PAGE_W - dw) / 2, (_PAGE_H - dh) / 2
    canvas = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {_PAGE_W:.0f} {_PAGE_H:.0f}" '
        f'width="{_PAGE_W:.0f}" height="{_PAGE_H:.0f}" font-family="{FONT}">'
        f'<rect width="{_PAGE_W:.0f}" height="{_PAGE_H:.0f}" fill="#FFFFFF"/>'
        f'<g transform="translate({ox:.2f},{oy:.2f}) scale({scale:.6f}) '
        f'translate({-vx:.2f},{-vy:.2f})">{wrapped}</g></svg>'
    )
    writer.append(PdfReader(io.BytesIO(cairosvg.svg2pdf(bytestring=canvas.encode()))))
    page = writer.pages[-1]
    pw, ph = float(page.mediabox.width), float(page.mediabox.height)
    # Annotation coords must follow the same fit-and-centre transform.
    sx = sy = scale * (pw / _PAGE_W)
    ox_pt, oy_pt = ox * (pw / _PAGE_W), oy * (ph / _PAGE_H)

    def _rect(x: float, y: float, w: float, h: float) -> ArrayObject:
        return ArrayObject(
            [
                FloatObject(ox_pt + (x - vx) * sx),
                FloatObject(ph - oy_pt - (y + h - vy) * sy),  # PDF y is bottom-up
                FloatObject(ox_pt + (x + w - vx) * sx),
                FloatObject(ph - oy_pt - (y - vy) * sy),
            ]
        )

    annots = ArrayObject()
    for x, y, w, h, url in links or []:
        annots.append(
            writer._add_object(
                DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/Annot"),
                        NameObject("/Subtype"): NameObject("/Link"),
                        NameObject("/Rect"): _rect(x, y, w, h),
                        NameObject("/Border"): ArrayObject(
                            [NumberObject(0), NumberObject(0), NumberObject(0)]
                        ),
                        NameObject("/A"): DictionaryObject(
                            {
                                NameObject("/S"): NameObject("/URI"),
                                NameObject("/URI"): TextStringObject(url),
                            }
                        ),
                    }
                )
            )
        )

    for x, y, w, h, tip in regions:
        rect = _rect(x, y, w, h)
        widget = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Btn"),
                NameObject("/Ff"): NumberObject(1 << 16),  # pushbutton (no value)
                NameObject("/T"): TextStringObject(f"tip{len(all_fields)}"),
                NameObject("/TU"): TextStringObject(tip),  # tooltip shown on hover
                NameObject("/Rect"): rect,
                NameObject("/F"): NumberObject(4),  # print
                NameObject("/MK"): DictionaryObject({}),  # invisible: no border/background
                NameObject("/BS"): DictionaryObject({NameObject("/W"): NumberObject(0)}),
                NameObject("/P"): page.indirect_reference,
            }
        )
        ref = writer._add_object(widget)
        annots.append(ref)
        all_fields.append(ref)
    page[NameObject("/Annots")] = annots


def export_report_pdf(
    data: PartnershipData,
    output_path: Path,
    taxonomy_path: str | Path,
) -> Path:
    """Export the external report as a two-page vector PDF with hover tooltips."""
    writer = PdfWriter()
    all_fields = ArrayObject()

    # Page 1 — title + introduction (no tooltips, no hover note)
    _add_page(writer, all_fields, _intro_svg(), [], with_note=False)

    # Page 2 — summary dashboard, with the investment note + disclaimer below it
    summary = compute_summary(data)
    ctx = _build_context(summary)
    dash = render_summary(summary)
    dash_svg = dash[dash.index("<svg") : dash.rindex("</svg>") + 6]
    dash_svg = _dashboard_with_captions(dash_svg)
    _add_page(writer, all_fields, dash_svg, _dashboard_regions(summary, ctx), with_note=False)

    # Page 3 — science-coverage treemap (landscape; height auto-fits the subfields),
    # preceded by its title, description, and how-to-read guidance.
    tree_svg, tree_regions = treemap_coverage_svg(data, taxonomy_path, width=1400)
    tree_svg, y_shift, tree_links = _treemap_with_header(tree_svg)
    tree_regions = [(x, y + y_shift, w, h, tip) for x, y, w, h, tip in tree_regions]
    _add_page(writer, all_fields, tree_svg, tree_regions, with_note=False, links=tree_links)

    writer._root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Fields"): all_fields,
                NameObject("/NeedAppearances"): BooleanObject(True),
            }
        )
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        writer.write(fh)
    return output_path


if __name__ == "__main__":
    import sys

    csv = sys.argv[1] if len(sys.argv) > 1 else "data/latest.csv"
    tax = sys.argv[2] if len(sys.argv) > 2 else "data/dwr_custom_taxonomy.csv"
    out = sys.argv[3] if len(sys.argv) > 3 else "reports/report.pdf"
    print(f"Wrote {export_report_pdf(PartnershipData(csv), Path(out), tax)}")
