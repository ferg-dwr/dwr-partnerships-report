# DWR Partnerships Report

[![CI](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/ci.yml/badge.svg)](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/ci.yml)
[![Report](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/generate-report.yml/badge.svg)](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/generate-report.yml)

Automated report pipeline for DWR Science & Technology Partnership data exported from Microsoft Lists. Upload a CSV → GitHub Actions diffs the data, flags anomalies, and publishes an updated interactive report to GitHub Pages.

**[View the live report →](https://ferg-dwr.github.io/dwr-partnerships-report/)**

---

## How it works

```
User exports CSV from Microsoft Lists
        ↓
Drag & drop into Upload UI (GitHub Pages)
        ↓
GitHub Contents API commits to data/latest.csv
        ↓
GitHub Actions triggers automatically on push to main
    ├── Diffs new CSV against previous commit
    ├── Runs ID watchdog (orphan + collision detection)
    ├── Creates GitHub Issue changelog with diff summary
    ├── Generates interactive HTML report
    │     ├── Science Field Coverage Gap (custom SVG treemap)
    │     ├── Science Field ↔ Staff ↔ Division (vis.js network)
    │     └── Division ↔ Partner Organization (vis.js network)
    └── Publishes to GitHub Pages via Pages artifact
```

The workflow triggers on changes to `data/latest.csv`, `templates/**`, or `dwr_report/**` — no manual trigger commits needed.

---

## For users: uploading new data

1. Export your partnerships list from Microsoft Lists as a CSV
2. Go to **[Upload UI →](https://ferg-dwr.github.io/dwr-partnerships-report/upload-ui/)**
3. Drag and drop your CSV, enter your GitHub PAT, and click Upload
4. Check the **[Actions tab](https://github.com/ferg-dwr/dwr-partnerships-report/actions)** — report regenerates in ~2 minutes
5. View the updated report at **[ferg-dwr.github.io/dwr-partnerships-report](https://ferg-dwr.github.io/dwr-partnerships-report/)**
6. A GitHub Issue is automatically created summarising new, removed, and updated partnerships

> Your token is never stored. It is used once to commit the CSV via the GitHub API and then discarded.

---

## Report features

### Science Field Coverage (treemap)
- Custom SVG treemap — no external charting library
- Blue hues from 1 → N partnerships; grey hatched cells = coverage gaps
- Grows vertically as the taxonomy expands — no horizontal squishing
- Click a category header to zoom in; click again to zoom out

### Organizational Network: Science ↔ Staff ↔ Division (tripartite)
- **POC self-service filter** — search your name to highlight all your partnerships
- Staff labels show `Last, F.` format with full name on hover
- Click any node to see connected science fields and divisions
- Accordion legend: How to use · Column Guide · Science Categories · Top 5 Staff · Top 5 Fields

### Organizational Network: DWR ↔ Partner Organizations (bipartite)
- Node size scales by total partnerships (degree-weighted)
- Click a node → expandable table of connected partners, colored by org type
- Click an edge → side-by-side entity header + flat partnership table
- Hover a table row → highlights that node in the network
- Accordion legend: How to use · Node Size · Partner Types · Top 5 Divisions · Top 5 Organizations

### Diff banner
- Shows new / removed / updated counts after each upload
- Collapsed per-partnership cards showing before → after field changes
- Collision warnings block publishing; orphan warnings are informational

---

## Repo structure

```
dwr-partnerships-report/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Lint + type-check + test on every push/PR
│       └── generate-report.yml     # Report pipeline
│
├── data/
│   ├── latest.csv                  # Current dataset — git history = full audit trail
│   └── dwr_custom_taxonomy.csv     # Science field taxonomy (categories + fields)
│
├── dwr_report/                     # Main Python package
│   ├── ingest/
│   │   ├── loader.py               # PartnershipData class + column normalization
│   │   └── taxonomy.py             # enrich_science_fields()
│   ├── charts/
│   │   ├── treemaps.py             # treemap_coverage() — renders treemap template
│   │   └── networks.py             # network_tripartite(), network_bipartite()
│   └── pipeline/
│       ├── diff.py                 # ID watchdog + change detection
│       ├── generate_report.py      # Orchestrator: data → charts → HTML report
│       └── create_issue.py         # GitHub Issue changelog on each upload
│
├── templates/
│   ├── report.html                 # Jinja2: main report page (header, nav, layout)
│   ├── treemap_coverage.html       # Custom SVG treemap (squarified layout)
│   ├── network_tripartite.html     # Jinja2 + vis.js: Science ↔ Staff ↔ Division
│   └── network_bipartite.html      # Jinja2 + vis.js: Division ↔ Partner Organization
│
├── tests/                          # 161 tests, ~92% coverage
│   ├── test_diff.py
│   ├── test_loader.py
│   ├── test_taxonomy.py
│   ├── test_treemaps.py
│   ├── test_networks.py
│   ├── test_generate_report.py
│   └── test_create_issue.py
│
├── upload-ui/
│   └── index.html                  # Drag-and-drop CSV uploader (GitHub Contents API)
│
├── pyproject.toml                  # ruff · mypy · pytest · setuptools
├── SETUP.md                        # First-time configuration guide
└── ROADMAP.md                      # Backlogged features and improvements
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
ruff format dwr_report/ tests/      # Format
ruff check dwr_report/ tests/       # Lint
mypy dwr_report/                    # Type check
pytest                              # Tests with coverage
```

### Running the report locally

```bash
mkdir -p reports
echo '{"new_ids":[],"removed_ids":[],"changed_rows":[],"warnings":[]}' > reports/diff.json

python dwr_report/pipeline/generate_report.py \
  --csv data/latest.csv \
  --diff reports/diff.json \
  --output reports/index.html \
  --taxonomy data/dwr_custom_taxonomy.csv

cd reports && python -m http.server 8000
```

> Hard-refresh (`Ctrl+Shift+R` / `Cmd+Shift+R`) after regenerating to bypass browser cache.

### Expanding the taxonomy

Edit `data/dwr_custom_taxonomy.csv` to add new science categories or fields. The treemap grows vertically to accommodate new entries — no layout code changes needed.

---

## ID watchdog

| Warning type | Meaning | Action |
|---|---|---|
| **Orphan** | An ID in the previous data is missing from the upload | Verify the partnership was intentionally deleted |
| **Collision** | A shared ID has a different organization name | Possible ID reuse — verify in Microsoft Lists before publishing |

Orphan warnings are informational. Collision warnings exit the workflow with code 2, blocking the report until resolved.

---

## GitHub Issue changelog

After every successful upload, a GitHub Issue is automatically created with:
- New / removed / updated partnership counts
- Per-partnership before → after field tables
- ID collision and orphan warnings

Labels (`data-update`, `new-partnerships`, `updated-partnerships`, `needs-review`) are created automatically, making the Issues tab a searchable change log over time.

---

## Branch strategy

- **`develop`** — active development; CI runs on every push
- **`main`** — production; pushes here trigger report generation and Pages deployment

---

## First-time setup

See **[SETUP.md](SETUP.md)** for step-by-step instructions on creating the repo, configuring the GitHub PAT secret, enabling Pages, and seeding the initial CSV.