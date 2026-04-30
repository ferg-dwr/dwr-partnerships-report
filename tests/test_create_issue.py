"""
tests/test_create_issue.py — Unit tests for dwr_report.pipeline.create_issue.

Note: create_issue() itself calls the gh CLI and is not unit tested here —
that requires a real GitHub token and is covered by the Actions workflow.
All pure-Python functions are fully tested.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dwr_report.pipeline.create_issue import (
    _format_value,
    build_issue_body,
    build_issue_labels,
    build_issue_title,
    create_issue,
)

EMPTY_DIFF: dict = {
    "new_ids": [],
    "removed_ids": [],
    "changed_rows": [],
    "warnings": [],
}

NEW_ONLY_DIFF: dict = {
    "new_ids": [51, 52, 53],
    "removed_ids": [],
    "changed_rows": [],
    "warnings": [],
}

FULL_DIFF: dict = {
    "new_ids": [51, 52],
    "removed_ids": [10],
    "changed_rows": [
        {
            "id": 5,
            "changes": [
                {"field": "Status of Partnership", "old": '["Active"]', "new": '["Inactive"]'},
                {
                    "field": "Main DWR Point of Contact",
                    "old": "Smith, Jane@DWR",
                    "new": "Garcia, Maria@DWR",
                },
            ],
        }
    ],
    "warnings": [],
}

COLLISION_DIFF: dict = {
    "new_ids": [],
    "removed_ids": [],
    "changed_rows": [],
    "warnings": [
        {"kind": "collision", "id": 5, "message": "Name changed from A to B"},
        {"kind": "orphan", "id": 10, "message": "ID missing from upload"},
    ],
}

SHA = "abc1234def5678"
REPO = "ferg-dwr/dwr-partnerships-report"
REPORT_URL = "https://ferg-dwr.github.io/dwr-partnerships-report/"


def write_diff(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "diff.json"
    p.write_text(json.dumps(data))
    return p


class TestFormatValue:
    def test_json_list_joined(self):
        assert _format_value('["Active"]') == "Active"

    def test_json_list_multiple_items(self):
        result = _format_value('["Hydrology", "Ecology"]')
        assert "Hydrology" in result
        assert "Ecology" in result

    def test_plain_string_unchanged(self):
        assert _format_value("Smith, Jane@DWR") == "Smith, Jane@DWR"

    def test_strips_brackets_from_non_json(self):
        result = _format_value("['Active']")
        assert "[" not in result
        assert "]" not in result

    def test_empty_list(self):
        assert _format_value("[]") == ""

    def test_invalid_json_returned_cleaned(self):
        result = _format_value("not json at all")
        assert isinstance(result, str)


class TestBuildIssueTitle:
    def test_contains_date(self):
        title = build_issue_title(EMPTY_DIFF)
        import re

        assert re.search(r"\d{4}-\d{2}-\d{2}", title)

    def test_no_changes_shows_no_changes(self):
        title = build_issue_title(EMPTY_DIFF)
        assert "no changes" in title

    def test_new_ids_in_title(self):
        title = build_issue_title(NEW_ONLY_DIFF)
        assert "+3 new" in title

    def test_removed_in_title(self):
        diff = {**EMPTY_DIFF, "removed_ids": [1, 2]}
        title = build_issue_title(diff)
        assert "-2 removed" in title

    def test_changed_in_title(self):
        title = build_issue_title(FULL_DIFF)
        assert "~1 updated" in title

    def test_collision_adds_warning_flag(self):
        title = build_issue_title(COLLISION_DIFF)
        assert "!" in title

    def test_no_warning_flag_without_collision(self):
        title = build_issue_title(FULL_DIFF)
        assert "!" not in title

    def test_multiple_parts_joined(self):
        title = build_issue_title(FULL_DIFF)
        assert "+2 new" in title
        assert "-1 removed" in title
        assert "~1 updated" in title


class TestBuildIssueLabels:
    def test_always_has_data_update(self):
        labels = build_issue_labels(EMPTY_DIFF)
        assert "data-update" in labels

    def test_new_ids_adds_label(self):
        labels = build_issue_labels(NEW_ONLY_DIFF)
        assert "new-partnerships" in labels

    def test_removed_ids_adds_label(self):
        diff = {**EMPTY_DIFF, "removed_ids": [1]}
        labels = build_issue_labels(diff)
        assert "removed-partnerships" in labels

    def test_changed_rows_adds_label(self):
        labels = build_issue_labels(FULL_DIFF)
        assert "updated-partnerships" in labels

    def test_collision_adds_needs_review(self):
        labels = build_issue_labels(COLLISION_DIFF)
        assert "needs-review" in labels

    def test_orphan_alone_no_needs_review(self):
        diff = {**EMPTY_DIFF, "warnings": [{"kind": "orphan", "id": 1, "message": "missing"}]}
        labels = build_issue_labels(diff)
        assert "needs-review" not in labels

    def test_empty_diff_only_data_update(self):
        labels = build_issue_labels(EMPTY_DIFF)
        assert labels == ["data-update"]


class TestBuildIssueBody:
    def test_contains_sha(self):
        body = build_issue_body(EMPTY_DIFF, SHA, REPORT_URL)
        assert SHA[:7] in body

    def test_contains_report_url(self):
        body = build_issue_body(EMPTY_DIFF, SHA, REPORT_URL)
        assert REPORT_URL in body

    def test_summary_table_present(self):
        body = build_issue_body(EMPTY_DIFF, SHA, REPORT_URL)
        assert "## Summary" in body
        assert "New partnerships" in body
        assert "Removed partnerships" in body
        assert "Updated partnerships" in body

    def test_new_ids_section(self):
        body = build_issue_body(NEW_ONLY_DIFF, SHA, REPORT_URL)
        assert "New Partnerships" in body
        assert "51" in body
        assert "52" in body
        assert "53" in body

    def test_removed_ids_section(self):
        diff = {**EMPTY_DIFF, "removed_ids": [10, 11]}
        body = build_issue_body(diff, SHA, REPORT_URL)
        assert "Removed Partnerships" in body
        assert "10" in body
        assert "11" in body

    def test_changed_rows_section(self):
        body = build_issue_body(FULL_DIFF, SHA, REPORT_URL)
        assert "Updated Partnerships" in body
        assert "ID 5" in body
        assert "Status of Partnership" in body

    def test_changed_rows_before_after(self):
        body = build_issue_body(FULL_DIFF, SHA, REPORT_URL)
        assert "Active" in body
        assert "Inactive" in body

    def test_changed_rows_collapsible(self):
        body = build_issue_body(FULL_DIFF, SHA, REPORT_URL)
        assert "<details>" in body
        assert "<summary>" in body

    def test_field_count_singular(self):
        diff = {
            **EMPTY_DIFF,
            "changed_rows": [
                {
                    "id": 1,
                    "changes": [
                        {"field": "Status of Partnership", "old": "Active", "new": "Inactive"}
                    ],
                }
            ],
        }
        body = build_issue_body(diff, SHA, REPORT_URL)
        assert "1 field changed" in body

    def test_field_count_plural(self):
        body = build_issue_body(FULL_DIFF, SHA, REPORT_URL)
        assert "2 fields changed" in body

    def test_collision_warning_section(self):
        body = build_issue_body(COLLISION_DIFF, SHA, REPORT_URL)
        assert "Collision" in body
        assert "manual review" in body

    def test_orphan_warning_section(self):
        body = build_issue_body(COLLISION_DIFF, SHA, REPORT_URL)
        assert "Removed IDs" in body

    def test_no_sections_when_empty(self):
        body = build_issue_body(EMPTY_DIFF, SHA, REPORT_URL)
        assert "New Partnerships" not in body
        assert "Removed Partnerships" not in body
        assert "Updated Partnerships" not in body

    def test_returns_string(self):
        body = build_issue_body(EMPTY_DIFF, SHA, REPORT_URL)
        assert isinstance(body, str)
        assert len(body) > 0


class TestCreateIssueSkip:
    def test_skips_when_empty_diff(self, tmp_path, capsys):
        p = write_diff(tmp_path, EMPTY_DIFF)
        create_issue(p, REPO, SHA)
        captured = capsys.readouterr()
        assert "skipping" in captured.out.lower()

    def test_skips_when_only_warnings_absent(self, tmp_path, capsys):
        """Warnings alone (orphans) should still trigger issue creation."""
        diff = {**EMPTY_DIFF, "warnings": [{"kind": "orphan", "id": 1, "message": "missing"}]}
        p = write_diff(tmp_path, diff)
        # Should NOT skip — orphan warnings are meaningful
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/issues/1", stderr=""
            )
            create_issue(p, REPO, SHA)
        captured = capsys.readouterr()
        assert "skipping" not in captured.out.lower()


class TestCreateIssueGhCli:
    def test_calls_gh_issue_create(self, tmp_path):
        p = write_diff(tmp_path, NEW_ONLY_DIFF)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/issues/1", stderr=""
            )
            create_issue(p, REPO, SHA)

        calls = [str(c) for c in mock_run.call_args_list]
        assert any("issue" in c and "create" in c for c in calls)

    def test_calls_gh_label_create(self, tmp_path):
        p = write_diff(tmp_path, NEW_ONLY_DIFF)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/issues/1", stderr=""
            )
            create_issue(p, REPO, SHA)

        calls = [str(c) for c in mock_run.call_args_list]
        assert any("label" in c and "create" in c for c in calls)

    def test_exits_on_gh_failure(self, tmp_path):
        p = write_diff(tmp_path, NEW_ONLY_DIFF)
        with patch("subprocess.run") as mock_run:
            # Label creation succeeds, issue creation fails
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),  # label
                MagicMock(returncode=0, stdout="", stderr=""),  # label
                MagicMock(returncode=1, stdout="", stderr="gh: authentication failed"),  # issue
            ]
            with pytest.raises(SystemExit):
                create_issue(p, REPO, SHA)

    def test_report_url_built_correctly(self, tmp_path):
        p = write_diff(tmp_path, NEW_ONLY_DIFF)
        bodies = []
        with patch("subprocess.run") as mock_run:

            def capture(*args, **kwargs):
                if "issue" in str(args) and "create" in str(args):
                    # Extract --body argument
                    call_args = args[0]
                    if "--body" in call_args:
                        idx = call_args.index("--body")
                        bodies.append(call_args[idx + 1])
                return MagicMock(returncode=0, stdout="https://github.com/issues/1", stderr="")

            mock_run.side_effect = capture
            create_issue(p, REPO, SHA)

        assert any(REPORT_URL in b for b in bodies)
