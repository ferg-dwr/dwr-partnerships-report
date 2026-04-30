"""
create_issue.py — Creates a GitHub Issue summarizing partnership data changes.

Called by GitHub Actions after each successful CSV upload and report generation.
Uses the gh CLI (available on all GitHub Actions runners) to create the issue.
Skips issue creation if there are no meaningful changes (empty diff).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _format_value(raw: str) -> str:
    """Clean up list-like strings for readable display."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return ", ".join(str(v).strip() for v in parsed)
    except (json.JSONDecodeError, TypeError):
        pass
    return str(raw).strip("[]'\"")


def build_issue_body(diff: dict, sha: str, report_url: str) -> str:
    new_ids = diff.get("new_ids", [])
    removed_ids = diff.get("removed_ids", [])
    changed_rows = diff.get("changed_rows", [])
    warnings = diff.get("warnings", [])

    collision_warnings = [w for w in warnings if w["kind"] == "collision"]
    orphan_warnings = [w for w in warnings if w["kind"] == "orphan"]

    date_str = datetime.now(UTC).strftime("%B %d, %Y at %H:%M UTC")
    short_sha = sha[:7]

    lines = [
        f"**Generated:** {date_str}  ",
        f"**Commit:** [`{short_sha}`](https://github.com/{diff.get('_repo', '')}/commit/{sha})  ",
        f"**Report:** {report_url}",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| | Count |",
        "|---|---|",
        f"| New partnerships | {len(new_ids)} |",
        f"| Removed partnerships | {len(removed_ids)} |",
        f"| Updated partnerships | {len(changed_rows)} |",
        "",
    ]

    # --- Warnings ---
    if collision_warnings:
        lines += [
            "## ⚠️ ID Collision Warnings",
            "",
            "> These require manual review before the report is considered reliable.",
            "",
        ]
        for w in collision_warnings:
            lines.append(f"- **ID {w['id']}:** {w['message']}")
        lines.append("")

    if orphan_warnings:
        lines += [
            "## i Removed IDs (verify intentional)",
            "",
        ]
        for w in orphan_warnings:
            lines.append(f"- **ID {w['id']}:** {w['message']}")
        lines.append("")

    # --- New partnerships ---
    if new_ids:
        lines += [
            "## New Partnerships",
            "",
            f"IDs added: {', '.join(str(i) for i in new_ids)}",
            "",
        ]

    # --- Removed partnerships ---
    if removed_ids:
        lines += [
            "## Removed Partnerships",
            "",
            f"IDs removed: {', '.join(str(i) for i in removed_ids)}",
            "",
        ]

    # --- Changed partnerships ---
    if changed_rows:
        lines += ["## Updated Partnerships", ""]
        for row in changed_rows:
            n = len(row["changes"])
            lines.append("<details>")
            lines.append(
                f"<summary><strong>ID {row['id']}</strong> — {n} field{'s' if n != 1 else ''} changed</summary>"
            )
            lines.append("")
            lines.append("| Field | Before | After |")
            lines.append("|---|---|---|")
            for c in row["changes"]:
                old_val = _format_value(c["old"])
                new_val = _format_value(c["new"])
                lines.append(f"| {c['field']} | {old_val} | {new_val} |")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)


def build_issue_title(diff: dict) -> str:
    new_count = len(diff.get("new_ids", []))
    removed_count = len(diff.get("removed_ids", []))
    changed_count = len(diff.get("changed_rows", []))
    warnings = diff.get("warnings", [])
    has_warnings = any(w["kind"] == "collision" for w in warnings)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    parts = []
    if new_count:
        parts.append(f"+{new_count} new")
    if removed_count:
        parts.append(f"-{removed_count} removed")
    if changed_count:
        parts.append(f"~{changed_count} updated")

    summary = ", ".join(parts) if parts else "no changes"
    warning_flag = "!" if has_warnings else ""
    return f"Data update {date_str} — {summary}{warning_flag}"


def build_issue_labels(diff: dict) -> list[str]:
    labels = ["data-update"]
    if diff.get("new_ids"):
        labels.append("new-partnerships")
    if diff.get("removed_ids"):
        labels.append("removed-partnerships")
    if diff.get("changed_rows"):
        labels.append("updated-partnerships")
    warnings = diff.get("warnings", [])
    if any(w["kind"] == "collision" for w in warnings):
        labels.append("needs-review")
    return labels


def create_issue(diff_path: Path, repo: str, sha: str) -> None:
    diff = json.loads(diff_path.read_text())

    # Skip if nothing changed
    if (
        not diff.get("new_ids")
        and not diff.get("removed_ids")
        and not diff.get("changed_rows")
        and not diff.get("warnings")
    ):
        print("No changes detected — skipping issue creation.")
        return

    report_url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/"
    title = build_issue_title(diff)
    body = build_issue_body(diff, sha, report_url)
    labels = build_issue_labels(diff)

    print(f"Creating issue: {title}")
    print(f"Labels: {labels}")

    # Ensure labels exist before creating the issue
    for label in labels:
        color_map = {
            "data-update": "0075ca",
            "new-partnerships": "2ea44f",
            "removed-partnerships": "d73a4a",
            "updated-partnerships": "e4a000",
            "needs-review": "b60205",
        }
        color = color_map.get(label, "ededed")
        subprocess.run(
            ["gh", "label", "create", label, "--color", color, "--repo", repo, "--force"],
            capture_output=True,
        )

    result = subprocess.run(
        [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--label",
            ",".join(labels),
            "--repo",
            repo,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Error creating issue: {result.stderr}")
        sys.exit(1)

    print(f"Issue created: {result.stdout.strip()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()

    create_issue(args.diff, args.repo, args.sha)