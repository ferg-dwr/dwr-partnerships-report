"""
diff.py — Partnership CSV diff and ID watchdog.

Compares an incoming CSV against the previous latest.csv and produces:
  - A structured DiffResult with new, removed, and changed partnerships
  - Warnings for ID anomalies (orphans, collisions, reuse)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

ID_COL = "ID"

# Fields used to detect meaningful changes (not just whitespace drift)
TRACKED_FIELDS = [
    "Partnership Organization Name",
    "Organization Type",
    "Relevant DWR Program(s) and/ or Project(s)",
    "Partnership Type",
    "Status of Partnership",
    "DWR Investments",
    "Science and Technology Fields",
    "DWR Division/ Office/ Branch",
    "Main DWR Point of Contact",
]

IDENTITY_FIELDS = ["Partnership Organization Name"]


@dataclass
class IDWarning:
    kind: str  # "orphan" | "collision" | "reuse"
    id_: int | float
    message: str


@dataclass
class FieldChange:
    field: str
    old_value: Any
    new_value: Any


@dataclass
class ChangedRow:
    id_: int | float
    changes: list[FieldChange]


@dataclass
class DiffResult:
    new_ids: list[int | float] = field(default_factory=list)
    removed_ids: list[int | float] = field(default_factory=list)
    changed_rows: list[ChangedRow] = field(default_factory=list)
    warnings: list[IDWarning] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def is_empty(self) -> bool:
        return not (self.new_ids or self.removed_ids or self.changed_rows)

    def summary(self) -> str:
        lines = ["=== Partnership Diff Summary ==="]
        lines.append(f"  New partnerships:     {len(self.new_ids)}")
        lines.append(f"  Removed partnerships: {len(self.removed_ids)}")
        lines.append(f"  Updated partnerships: {len(self.changed_rows)}")

        if self.new_ids:
            lines.append(f"\n  New IDs: {self.new_ids}")

        if self.removed_ids:
            lines.append(f"\n  Removed IDs: {self.removed_ids}")

        if self.changed_rows:
            lines.append("\n  Changes:")
            for row in self.changed_rows:
                lines.append(f"    ID {row.id_}:")
                for ch in row.changes:
                    lines.append(f"      {ch.field}")
                    lines.append(f"        Before: {ch.old_value}")
                    lines.append(f"        After:  {ch.new_value}")

        if self.warnings:
            lines.append("\n⚠️  ID WARNINGS — review before publishing:")
            for w in self.warnings:
                lines.append(f"  [{w.kind.upper()}] ID {w.id_}: {w.message}")

        return "\n".join(lines)


def _normalize_colname(col: str) -> str:
    return " ".join(str(col).strip().split())


def _to_list_if_listlike(x: Any) -> Any:
    if isinstance(x, list):
        return x
    if pd.isna(x):
        return []
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip() != ""]
            except Exception:
                pass
    return x


def _canonical(value: Any) -> str:
    """Normalize a cell value to a stable string for comparison."""
    v = _to_list_if_listlike(value)
    if isinstance(v, list):
        return str(sorted(str(i).strip() for i in v))
    return str(v).strip()


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df.columns = [_normalize_colname(c) for c in df.columns]
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
    if ID_COL in df.columns:
        df[ID_COL] = pd.to_numeric(df[ID_COL], errors="coerce")
    return df


def diff_csvs(old_path: Path | str, new_path: Path | str) -> DiffResult:
    """
    Compare old_path (previous latest.csv) against new_path (incoming upload).

    Returns a DiffResult with all changes and any ID warnings.
    """
    old_path = Path(old_path)
    new_path = Path(new_path)

    result = DiffResult()

    old_df = _load(old_path).set_index(ID_COL)
    new_df = _load(new_path).set_index(ID_COL)

    old_ids = set(old_df.index.dropna())
    new_ids = set(new_df.index.dropna())

    result.new_ids = sorted(new_ids - old_ids)
    result.removed_ids = sorted(old_ids - new_ids)

    for id_ in result.removed_ids:
        result.warnings.append(
            IDWarning(
                kind="orphan",
                id_=id_,
                message=(
                    f"ID {id_} was present in the previous data but is missing from the upload. "
                    "This is expected if the partnership was deleted. If not intentional, "
                    "the ID may have been reassigned — check Microsoft Lists."
                ),
            )
        )

    shared_ids = old_ids & new_ids
    for id_ in sorted(shared_ids):
        old_row = old_df.loc[id_]
        new_row = new_df.loc[id_]

        for identity_field in IDENTITY_FIELDS:
            if identity_field not in old_df.columns or identity_field not in new_df.columns:
                continue
            old_val = _canonical(old_row.get(identity_field, ""))
            new_val = _canonical(new_row.get(identity_field, ""))
            if old_val and new_val and old_val != new_val:
                result.warnings.append(
                    IDWarning(
                        kind="collision",
                        id_=id_,
                        message=(
                            f"Identity field '{identity_field}' changed from "
                            f"'{old_val}' → '{new_val}'. "
                            "Possible ID reuse or collision — verify this is an intentional rename."
                        ),
                    )
                )

    tracked = [f for f in TRACKED_FIELDS if f in old_df.columns and f in new_df.columns]
    for id_ in sorted(shared_ids):
        old_row = old_df.loc[id_]
        new_row = new_df.loc[id_]
        changes = []
        for col in tracked:
            old_val = _canonical(old_row.get(col, ""))
            new_val = _canonical(new_row.get(col, ""))
            if old_val != new_val:
                changes.append(
                    FieldChange(
                        field=col,
                        old_value=_to_list_if_listlike(old_row.get(col, "")),
                        new_value=_to_list_if_listlike(new_row.get(col, "")),
                    )
                )
        if changes:
            result.changed_rows.append(ChangedRow(id_=id_, changes=changes))

    return result


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 4:
        print("Usage: python diff.py <old_csv> <new_csv> <output_json>")
        sys.exit(1)

    old_csv, new_csv, output_json = sys.argv[1], sys.argv[2], sys.argv[3]
    result = diff_csvs(old_csv, new_csv)

    print(result.summary())

    # Write machine-readable output for the report generator
    out = {
        "new_ids": result.new_ids,
        "removed_ids": result.removed_ids,
        "changed_rows": [
            {
                "id": r.id_,
                "changes": [
                    {"field": c.field, "old": str(c.old_value), "new": str(c.new_value)}
                    for c in r.changes
                ],
            }
            for r in result.changed_rows
        ],
        "warnings": [{"kind": w.kind, "id": w.id_, "message": w.message} for w in result.warnings],
    }
    Path(output_json).write_text(json.dumps(out, indent=2))
    print(f"\nDiff written to {output_json}")

    # Exit with error code if there are collision warnings — blocks report publish
    collision_warnings = [w for w in result.warnings if w.kind == "collision"]
    if collision_warnings:
        print("\n❌ Collision warnings detected. Resolve before publishing.")
        sys.exit(2)
