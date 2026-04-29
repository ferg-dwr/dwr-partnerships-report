"""
tests/test_diff.py — Unit tests for the diff + ID watchdog module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dwr_report.pipeline.diff import (
    _canonical,
    _to_list_if_listlike,
    diff_csvs,
)


def write_csv(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    """Write a list of dicts to a CSV file and return the path."""
    p = tmp_path / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


BASE_ROW = {
    "ID": 1,
    "Partnership Organization Name": "UC Davis",
    "Organization Type": "['University']",
    "Relevant DWR Program(s) and/ or Project(s)": "['Delta Science']",
    "Partnership Type": "['Research']",
    "Status of Partnership": "['Active']",
    "DWR Investments": "['Funding']",
    "Science and Technology Fields": "['Hydrology']",
    "DWR Division/ Office/ Branch": "['Delta']",
    "Main DWR Point of Contact": "Jane Smith",
}


class TestToListIfListlike:
    def test_already_a_list(self):
        assert _to_list_if_listlike(["a", "b"]) == ["a", "b"]

    def test_json_string(self):
        assert _to_list_if_listlike('["UC Davis", "NOAA"]') == ["UC Davis", "NOAA"]

    def test_python_string(self):
        assert _to_list_if_listlike("['A', 'B']") == ["A", "B"]

    def test_empty_string(self):
        assert _to_list_if_listlike("") == []

    def test_nan(self):

        result = _to_list_if_listlike(float("nan"))
        assert result == []

    def test_plain_string_unchanged(self):
        assert _to_list_if_listlike("Jane Smith") == "Jane Smith"

    def test_strips_whitespace_from_items(self):
        assert _to_list_if_listlike("['  A  ', ' B']") == ["A", "B"]

    def test_filters_empty_items(self):
        assert _to_list_if_listlike("['A', '', 'B']") == ["A", "B"]


class TestCanonical:
    def test_list_is_sorted(self):
        assert _canonical(["B", "A"]) == _canonical(["A", "B"])

    def test_list_string_matches_list(self):
        assert _canonical('["Hydrology", "Ecology"]') == _canonical(["Ecology", "Hydrology"])

    def test_plain_string(self):
        assert _canonical("Jane Smith") == "Jane Smith"

    def test_strips_whitespace(self):
        assert _canonical("  Jane Smith  ") == "Jane Smith"


class TestDiffNoChanges:
    def test_identical_files_empty_diff(self, tmp_path):
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [BASE_ROW])
        result = diff_csvs(old, new)
        assert result.is_empty
        assert not result.has_warnings

    def test_whitespace_only_diff_ignored(self, tmp_path):
        row = {**BASE_ROW, "Main DWR Point of Contact": "  Jane Smith  "}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [row])
        result = diff_csvs(old, new)
        assert result.is_empty


class TestDiffNewRemoved:
    def test_new_id_detected(self, tmp_path):
        row2 = {**BASE_ROW, "ID": 2, "Partnership Organization Name": "NOAA"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [BASE_ROW, row2])
        result = diff_csvs(old, new)
        assert 2 in result.new_ids
        assert result.removed_ids == []

    def test_removed_id_detected(self, tmp_path):
        row2 = {**BASE_ROW, "ID": 2, "Partnership Organization Name": "NOAA"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW, row2])
        new = write_csv(tmp_path, "new.csv", [BASE_ROW])
        result = diff_csvs(old, new)
        assert 2 in result.removed_ids
        assert result.new_ids == []

    def test_removed_id_triggers_orphan_warning(self, tmp_path):
        row2 = {**BASE_ROW, "ID": 2, "Partnership Organization Name": "NOAA"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW, row2])
        new = write_csv(tmp_path, "new.csv", [BASE_ROW])
        result = diff_csvs(old, new)
        kinds = [w.kind for w in result.warnings]
        assert "orphan" in kinds

    def test_multiple_new_ids(self, tmp_path):
        extra = [
            {**BASE_ROW, "ID": i, "Partnership Organization Name": f"Org {i}"} for i in range(2, 6)
        ]
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [BASE_ROW, *extra])
        result = diff_csvs(old, new)
        assert sorted(result.new_ids) == [2, 3, 4, 5]


class TestDiffFieldChanges:
    def test_changed_field_detected(self, tmp_path):
        updated = {**BASE_ROW, "Status of Partnership": "['Inactive']"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [updated])
        result = diff_csvs(old, new)
        assert len(result.changed_rows) == 1
        fields_changed = [c.field for c in result.changed_rows[0].changes]
        assert "Status of Partnership" in fields_changed

    def test_unchanged_fields_not_reported(self, tmp_path):
        updated = {**BASE_ROW, "Status of Partnership": "['Inactive']"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [updated])
        result = diff_csvs(old, new)
        fields_changed = [c.field for c in result.changed_rows[0].changes]
        assert "Main DWR Point of Contact" not in fields_changed

    def test_list_order_change_not_reported(self, tmp_path):
        """Reordering items in a list field should not count as a change."""
        old_row = {**BASE_ROW, "Science and Technology Fields": "['Hydrology', 'Ecology']"}
        new_row = {**BASE_ROW, "Science and Technology Fields": "['Ecology', 'Hydrology']"}
        old = write_csv(tmp_path, "old.csv", [old_row])
        new = write_csv(tmp_path, "new.csv", [new_row])
        result = diff_csvs(old, new)
        assert result.is_empty

    def test_multiple_fields_changed(self, tmp_path):
        updated = {
            **BASE_ROW,
            "Status of Partnership": "['Inactive']",
            "Main DWR Point of Contact": "Bob Jones",
        }
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [updated])
        result = diff_csvs(old, new)
        fields_changed = [c.field for c in result.changed_rows[0].changes]
        assert "Status of Partnership" in fields_changed
        assert "Main DWR Point of Contact" in fields_changed


class TestDiffCollisionWarnings:
    def test_identity_field_change_triggers_collision_warning(self, tmp_path):
        updated = {**BASE_ROW, "Partnership Organization Name": "NOAA — totally different org"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [updated])
        result = diff_csvs(old, new)
        kinds = [w.kind for w in result.warnings]
        assert "collision" in kinds

    def test_no_collision_warning_for_minor_update(self, tmp_path):
        """Changing a non-identity field should not trigger a collision warning."""
        updated = {**BASE_ROW, "Status of Partnership": "['Inactive']"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [updated])
        result = diff_csvs(old, new)
        kinds = [w.kind for w in result.warnings]
        assert "collision" not in kinds


class TestDiffResultSummary:
    def test_summary_contains_counts(self, tmp_path):
        row2 = {**BASE_ROW, "ID": 2, "Partnership Organization Name": "NOAA"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [BASE_ROW, row2])
        result = diff_csvs(old, new)
        summary = result.summary()
        assert "New partnerships" in summary
        assert "1" in summary

    def test_empty_diff_summary(self, tmp_path):
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [BASE_ROW])
        result = diff_csvs(old, new)
        summary = result.summary()
        assert "0" in summary


class TestDiffCLI:
    def test_cli_writes_json(self, tmp_path):
        row2 = {**BASE_ROW, "ID": 2, "Partnership Organization Name": "NOAA"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [BASE_ROW, row2])
        out_json = tmp_path / "diff.json"

        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "dwr_report/pipeline/diff.py", str(old), str(new), str(out_json)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out_json.read_text())
        assert 2 in data["new_ids"]
        assert data["warnings"] == []

    def test_cli_exits_2_on_collision(self, tmp_path):
        updated = {**BASE_ROW, "Partnership Organization Name": "Completely Different Org"}
        old = write_csv(tmp_path, "old.csv", [BASE_ROW])
        new = write_csv(tmp_path, "new.csv", [updated])
        out_json = tmp_path / "diff.json"

        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "dwr_report/pipeline/diff.py", str(old), str(new), str(out_json)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
