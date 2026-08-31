"""
content.py — Shared narrative content for the external report.

Single source of truth for the title, introduction, and figure notes so the
HTML report (templates/report.html) and the PDF export (pipeline/export_pdf.py)
render the same text. Edit here to change the wording in both places.
"""

REPORT_ORG = "California Department of Water Resources"
REPORT_TITLE = "2026 Science & Technology Partnerships Report"

# ---------------------------------------------------------------------------
# Terminology
#
# Two different quantities appear in this report and must never be conflated:
#
#   119  rows in the inventory                    -> partnership initiatives
#   437  science-field assignments across them    -> science field tags
#
# One initiative tagged with four science fields contributes four field tags,
# so the treemap totals are always >= the initiative count. Every label that
# shows one of these numbers pulls its wording from the constants below, so the
# vocabulary can be changed in one place if Lindsay prefers different terms.
# ---------------------------------------------------------------------------
TERM_INITIATIVES = "Partnership Initiatives"
TERM_INITIATIVES_LOWER = "partnership initiatives"
TERM_INITIATIVE_SINGULAR = "partnership initiative"
TERM_FIELD_TAGS = "Science Field Tags"
TERM_FIELD_TAGS_LOWER = "science field tags"
TERM_FIELD_TAG_SINGULAR = "science field tag"


def plural_initiatives(n: int) -> str:
    """'1 partnership initiative' / '4 partnership initiatives'."""
    return f"{n} {TERM_INITIATIVE_SINGULAR if n == 1 else TERM_INITIATIVES_LOWER}"


def plural_field_tags(n: int) -> str:
    """'1 science field tag' / '98 science field tags'."""
    return f"{n} {TERM_FIELD_TAG_SINGULAR if n == 1 else TERM_FIELD_TAGS_LOWER}"


# ---------------------------------------------------------------------------
# External links
# ---------------------------------------------------------------------------
# Science field taxonomy definitions (supplied by Lindsay, July 2026).
TAXONOMY_URL = "https://cadwr.app.box.com/s/bq56dj39aqzb5cc526ewcul5v5606eew"
TAXONOMY_LINK_TEXT = "Science field definitions"

# Wording for subfields with no tagged initiatives. "Coverage gap" read as a
# judgement about DWR's programme; this is purely descriptive.
TERM_NO_PARTNERSHIPS = "No Recorded Partnerships"
TERM_NO_PARTNERSHIPS_LOWER = "no recorded partnerships"

# Public partnerships dashboard, referenced in the introduction.
# LEAVE EMPTY until the URL is confirmed — an empty value keeps Lindsay's
# visible "[add link]" placeholder in the copy so it cannot ship unnoticed.
# Empty until Lindsay supplies it. While empty the reference is simply omitted
# rather than printing a visible placeholder into a distributed report.
DASHBOARD_URL = ""
_DASHBOARD_REF = f" ({DASHBOARD_URL})" if DASHBOARD_URL else ""

INTRO_HEADING = "Background and Purpose"
INTRO_PARAGRAPHS = [
    "The California Department of Water Resources engages in Science and Technology "
    "partnerships with academic, tribal, federal and State agency, non-profit, and "
    "private sector organizations. Partnership types range from contractual agreements, "
    "in-kind support, to advisory committee participation. As a large organization with "
    "many science and engineering staff, the partnerships are evolving. In 2025, DWR "
    f"established an inventory and dashboard{_DASHBOARD_REF} of its partnerships based on "
    "self-reported data from DWR leads for science and technology initiatives since 2020 "
    "(active or inactive). While the dashboard is updated annually with some ongoing "
    "inputs, the partnerships shown are not comprehensive and may not accurately reflect "
    "partnership status.",
    "This supplemental report offers a snapshot of DWR's science and technology "
    "partnerships at time of publication, which enables measuring partnership changes "
    "over time. It also includes additional supplemental figures that highlight the "
    "diversity, concentration, and gaps in science partnership fields.",
]
CONTACT_PREFIX = (
    "For more information on DWR Science and Technology partnerships and this report, "
    "please contact"
)
CONTACT_EMAIL = "dwrscience@water.ca.gov"

# Caption explaining the investment types shown in the dashboard.
INVESTMENT_NOTE = (
    "Partnerships can involve financial investment from DWR, in-kind support (DWR staff "
    "time to support partnership activities), or both. Scoping partnerships are in "
    "progress with in-kind support, but without a dedicated partnership activity. "
    "Because a single partnership can be counted in more than one category, these bars "
    f"add up to more than the total number of {TERM_INITIATIVES_LOWER}."
)
# Footnote on the Financial Investment figure (marked with * on that figure).
FINANCIAL_DISCLAIMER = "Self-reported relevant contract amount, not specific to year."

# ---------------------------------------------------------------------------
# Science coverage treemap — title, description, and how-to-read guidance
# ---------------------------------------------------------------------------
TREEMAP_TITLE = "Science Field Coverage and Gaps"

TREEMAP_DESCRIPTION = (
    f"This figure shows DWR's {TERM_INITIATIVES_LOWER} organized by the DWR taxonomy of "
    "science fields. The taxonomy has two levels: eight broad science categories, each "
    "containing a set of more specific science subfields."
)

# Explains why the treemap total does not match the dashboard's initiative count.
# See TERM_* above — this is the 437-vs-119 explanation Lindsay asked for.
TREEMAP_COUNTING_NOTE = (
    f"Each {TERM_INITIATIVE_SINGULAR} can be tagged with more than one science field, so "
    f"the totals here count field tags, not initiatives. The {TERM_FIELD_TAGS_LOWER} shown "
    f"in this figure are spread across the {TERM_INITIATIVES_LOWER} in the inventory, which "
    "is why this number is larger than the partnership count on the dashboard."
)

TREEMAP_HOW_TO_READ = [
    "Each rectangle is a science subfield, grouped under its science category.",
    "A rectangle's size and color both show how many partnership initiatives are "
    "tagged with that subfield — larger and darker means more.",
    "Grey hatched rectangles have no recorded partnerships: subfields in the "
    "taxonomy that no partnership initiative is currently tagged with.",
    "This figure shows where partnerships exist across fields, not how large, "
    "well-funded, or active any individual partnership is.",
]
