"""
tests/test_content.py — Guards on the shared report vocabulary.

Two quantities in this report are routinely confused: the count of partnership
initiatives (rows in the inventory) and the count of science field tags (field
assignments across those rows). Every label that displays either number pulls
from these constants, so they are the single point where the distinction is
enforced.
"""

from __future__ import annotations

from dwr_report import content


class TestPluralHelpers:
    def test_initiatives_singular_and_plural(self):
        assert content.plural_initiatives(1) == "1 partnership initiative"
        assert content.plural_initiatives(4) == "4 partnership initiatives"
        assert content.plural_initiatives(0) == "0 partnership initiatives"

    def test_field_tags_singular_and_plural(self):
        assert content.plural_field_tags(1) == "1 science field tag"
        assert content.plural_field_tags(437) == "437 science field tags"


class TestVocabulary:
    def test_the_two_quantities_use_different_nouns(self):
        """If these ever collide, the labels stop distinguishing anything."""
        assert content.TERM_INITIATIVES != content.TERM_FIELD_TAGS
        assert content.TERM_INITIATIVES_LOWER not in content.TERM_FIELD_TAGS_LOWER

    def test_taxonomy_url_is_set(self):
        assert content.TAXONOMY_URL.startswith("https://")


class TestDashboardReference:
    def test_no_placeholder_text_ever_reaches_the_report(self):
        """The draft marker must never appear in a distributed report."""
        body = " ".join(content.INTRO_PARAGRAPHS)
        assert "[add link]" not in body
        assert "add link" not in body

    def test_url_is_included_once_supplied(self):
        """While DASHBOARD_URL is empty the reference is simply omitted; setting
        it should splice the URL into the introduction without leaving artefacts."""
        body = " ".join(content.INTRO_PARAGRAPHS)
        if content.DASHBOARD_URL:
            assert content.DASHBOARD_URL in body
        else:
            assert "inventory and dashboard of its partnerships" in body
