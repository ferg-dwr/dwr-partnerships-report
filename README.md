# DWR Partnerships Report

[![CI](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/ci.yml/badge.svg)](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/ci.yml)

Automated report generation for DWR partnership data exported from Microsoft Lists.
Upload a CSV → GitHub Actions diffs the data, flags anomalies, and publishes an updated report to GitHub Pages.

---

## How it works

```
User downloads CSV from Microsoft Lists
        ↓
Drag & drop into upload UI (GitHub Pages)
        ↓
GitHub Contents API commits to data/latest.csv
        ↓
GitHub Actions triggers automatically
    ├── Diffs new CSV against previous commit
    ├── Runs ID watchdog (orphan + collision detection)
    ├── Generates interactive HTML report
    └── Publishes to GitHub Pages
```

---

## For users: uploading new data

1. Export your partnerships list from Microsoft Lists as a CSV
2. Go to the **[Upload UI](https://ferg-dwr.github.io/dwr-partnerships-report/upload-ui/)**
3. Drag and drop your CSV, enter your GitHub token, and click Upload
4. Check the **[Actions tab](https://github.com/ferg-dwr/dwr-partnerships-report/actions)** — report regenerates in ~2 minutes
5. View the updated report at the **[report page](https://ferg-dwr.github.io/dwr-partnerships-report/)**

> The upload UI never stores your token. It is used once to commit the file and then discarded.

---

## Repo structure

```
dwr-partnerships-report/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Lint, type-check, test on every push/PR
│       └── generate-report.yml     # Report pipeline (triggers on data/latest.csv change)
├── data/
│   └── latest.csv                  # Current dataset — git history = full audit trail
├── src/
│   ├── report_chart.py             # ReportChart class: treemaps, network graphs
│   ├── diff.py                     # ID watchdog + change detection
│   └── generate_report.py          # Orchestration: loads data → charts → HTML report
├── tests/
│   ├── conftest.py
│   └── test_diff.py                # Unit tests for diff logic
├── upload-ui/
│   └── index.html                  # Drag-and-drop CSV uploader (no Git required)
├── templates/                      # Jinja2 templates for network graphs
├── reports/                        # Auto-generated HTML (committed by Actions)
├── pyproject.toml                  # Project config: ruff, mypy, pytest
└── SETUP.md                        # First-time configuration guide
```

---

## For developers

### Prerequisites

- Python 3.11+
- Git

### Local setup

```bash
git clone git@github.com-fergDWR:ferg-dwr/dwr-partnerships-report.git
cd dwr-partnerships-report
pip install -e ".[dev]"
```

### Running checks locally

```bash
ruff format src/ tests/     # Format
ruff check src/ tests/      # Lint
mypy src/diff.py src/generate_report.py  # Type check
pytest                      # Tests with coverage
```

All three are enforced by CI on every push and pull request.

### Running the report locally

```bash
python src/diff.py data/previous.csv data/latest.csv reports/diff.json
python src/generate_report.py \
  --csv data/latest.csv \
  --diff reports/diff.json \
  --output reports/index.html
```

---

## ID watchdog

| Warning type | What it means | Action |
|---|---|---|
| **Orphan** | An ID in the previous data is missing from the upload | Verify the partnership was intentionally deleted |
| **Collision** | A shared ID has a different organization name | Possible ID reuse — check Microsoft Lists before publishing |

Orphan warnings are informational. Collision warnings block the report from publishing (Actions exits with code 2).

---