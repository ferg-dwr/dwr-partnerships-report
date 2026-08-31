"""
tests/test_export_pdf.py — Unit tests for dwr_report.pipeline.export_pdf.

The PDF path had no coverage at all before these tests, which is also where
Lindsay Correa's July 2026 terminology fixes live. cairosvg and pypdf are
optional extras (`pip install -e ".[pdf]"`), so the whole module skips cleanly
when they're absent rather than failing a dev machine that never needs them.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dwr_report import content
from dwr_report.ingest.loader import PartnershipData
from dwr_report.ingest.taxonomy import enrich_science_fields

pytest.importorskip("cairosvg", reason="PDF export needs the [pdf] extra")
pytest.importorskip("pypdf", reason="PDF export needs the [pdf] extra")

from dwr_report.pipeline.export_pdf import export_report_pdf

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ROWS = [
    {
        "ID": 1,
        "Partnership Organization Name": '["UC Davis"]',
        "Organization Type": '["University"]',
        "Relevant DWR Program(s) and/ or Project(s)": '["Delta Science"]',
        "Partnership Type": '["Research"]',
        "Status of Partnership": '["Active"]',
        "DWR Investments": '["Financial Support"]',
        "Science and Technology Fields": '["Hydrology", "Climatology"]',
        "DWR Division/ Office/ Branch": "Flood Operations",
        "Main DWR Point of Contact": "Smith, Jane@DWR",
    },
    {
        "ID": 2,
        "Partnership Organization Name": '["Sunrise Water Institute"]',
        "Organization Type": '["NGO"]',
        "Relevant DWR Program(s) and/ or Project(s)": '["Snow Survey"]',
        "Partnership Type": '["Advisory"]',
        "Status of Partnership": '["Active"]',
        "DWR Investments": '["In-kind Support"]',
        "Science and Technology Fields": '["Hydrology"]',
        "DWR Division/ Office/ Branch": "Hydrology Branch",
        "Main DWR Point of Contact": "Doe, John@DWR",
    },
]

TAXONOMY_ROWS = [
    {
        "1st Level (Science Category)": "Geological and Earth Sciences",
        "2nd level (Science Field)": "Hydrology",
        "Description": "",
    },
    {
        "1st Level (Science Category)": "Atmospheric Sciences",
        "2nd level (Science Field)": "Climatology",
        "Description": "",
    },
    {
        "1st Level (Science Category)": "Atmospheric Sciences",
        "2nd level (Science Field)": "Meteorology",
        "Description": "",
    },
]


@pytest.fixture
def built_pdf(tmp_path: Path) -> Path:
    """Render a real PDF once and share it across assertions."""
    csv_p = tmp_path / "data.csv"
    pd.DataFrame(ROWS).to_csv(csv_p, index=False)
    tax_p = tmp_path / "tax.csv"
    pd.DataFrame(TAXONOMY_ROWS).to_csv(tax_p, index=False)

    data = PartnershipData(csv_p)
    enrich_science_fields(data, tax_p)
    return export_report_pdf(data, tmp_path / "report.pdf", tax_p)


def _reader(path: Path):
    from pypdf import PdfReader

    return PdfReader(str(path))


def _squash(text: str) -> str:
    """Strip all whitespace so assertions survive pypdf version differences.

    pypdf infers word spacing from glyph positions and the heuristic changed
    between 5.x and 6.x: 6.14 extracts the small grey disclaimer run as
    "Self-reportedrelevantcontractamount". The text is correct in the PDF
    (pdftotext reads it fine), so comparisons ignore spacing entirely.
    """
    return "".join(text.split())


def _page_text(path: Path, index: int) -> str:
    return _squash(_reader(path).pages[index].extract_text())


def _all_text(path: Path) -> str:
    return _squash("".join(p.extract_text() for p in _reader(path).pages))


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestPdfStructure:
    def test_writes_a_readable_pdf(self, built_pdf):
        assert built_pdf.exists()
        assert built_pdf.stat().st_size > 1000

    def test_has_three_pages(self, built_pdf):
        """Intro, summary dashboard, science-field treemap."""
        assert len(_reader(built_pdf).pages) == 3

    def test_figure_pages_carry_hover_tooltips(self, built_pdf):
        """Tooltips are /Widget annots; the intro page has none by design."""
        pages = _reader(built_pdf).pages
        counts = [len(p.get("/Annots") or []) for p in pages]
        assert counts[0] == 0
        assert counts[1] > 0
        assert counts[2] > 0


# ---------------------------------------------------------------------------
# Lindsay's July 2026 review
# ---------------------------------------------------------------------------


class TestReviewFixes:
    def test_intro_and_disclaimers_are_present(self, built_pdf):
        text = _all_text(built_pdf)
        assert _squash(content.INTRO_HEADING) in text
        assert _squash(content.FINANCIAL_DISCLAIMER) in text
        assert _squash("in-kind support") in text.lower()

    def test_treemap_page_has_title_and_how_to_read(self, built_pdf):
        page = _page_text(built_pdf, 2)
        assert _squash(content.TREEMAP_TITLE) in page
        assert _squash("How to read this figure") in page

    def test_treemap_page_explains_field_tags_versus_initiatives(self, built_pdf):
        """The 437-vs-119 explanation Lindsay asked for."""
        page = _page_text(built_pdf, 2)
        assert _squash(content.TERM_FIELD_TAGS_LOWER) in page
        assert _squash(content.TERM_INITIATIVES_LOWER) in page

    def test_taxonomy_url_is_a_clickable_link_annotation(self, built_pdf):
        """Not just printed text — a real /Link annot with a URI action."""
        annots = [a.get_object() for a in (_reader(built_pdf).pages[2].get("/Annots") or [])]
        links = [a for a in annots if a.get("/Subtype") == "/Link"]
        assert len(links) == 1
        assert links[0]["/A"]["/URI"] == content.TAXONOMY_URL

    def test_stat_card_says_initiatives_not_partnerships(self, built_pdf):
        """The 119 is a distinct-row count; its label must say so."""
        page = _page_text(built_pdf, 1)
        assert _squash(content.TERM_INITIATIVES) in page

    def test_treemap_totals_are_labelled_field_tags(self, built_pdf):
        page = _page_text(built_pdf, 2)
        assert _squash(content.TERM_FIELD_TAGS).upper() in page.upper()
        # The negative guard — that the grand total is not labelled PARTNERSHIPS
        # on its own — lives in test_treemaps.py against the SVG, where element
        # boundaries are exact. Extracted PDF text has no reliable delimiters.
