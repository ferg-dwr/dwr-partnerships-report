# DWR Partnerships Report

[![CI](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/ci.yml/badge.svg)](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/ci.yml)
[![Report](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/generate-report.yml/badge.svg)](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/generate-report.yml)

Automated report pipeline for DWR Science & Technology Partnership data exported from Microsoft Lists. Upload a CSV → GitHub Actions diffs the data, flags anomalies, and publishes an updated interactive report to GitHub Pages plus a supplemental PDF.

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
    │     ├── Science Field Coverage (custom SVG treemap)
    │     ├── Science Field ↔ Staff ↔ Division (vis.js network)
    │     └── Division ↔ Partner Organization (vis.js network)
    ├── Exports a 3-page supplemental PDF
    └── Publishes to GitHub Pages via Pages artifact
```

The workflow triggers on changes to `data/**`, `templates/**`, or `src/dwr_report/**` — no manual trigger commits needed.

---

## Terminology

Two quantities in this report are easy to conflate, and the distinction is load-bearing:

| Term | Count | What it measures |
|---|---|---|
| **Partnership initiatives** | 119 | Rows in the inventory |
| **Science field tags** | 437 | Field assignments across those rows |

A single initiative tagged with four science fields contributes four field tags, so the treemap totals are always greater than or equal to the partnership count on the dashboard. Every label displaying either number pulls from shared constants in `src/dwr_report/content.py`, which is the one place to change the wording.

---

## For users: uploading new data

1. Export your partnerships list from Microsoft Lists as a CSV
2. Go to **[Upload UI →](https://ferg-dwr.github.io/dwr-partnerships-report/upload-ui/)**
3. Drag and drop your CSV, enter your GitHub PAT, and click Upload
4. Check the **[Actions tab](https://github.com/ferg-dwr/dwr-partnerships-report/actions)** — report regenerates in ~2 minutes
5. View the updated report at **[ferg-dwr.github.io/dwr-partnerships-report](https://ferg-dwr.github.io/dwr-partnerships-report/)**
6. A GitHub Issue is automatically created summarising new, removed, and updated partnerships

> Your token is never stored. It is used once to commit the CSV via the GitHub API and then discarded. The upload UI is served from GitHub Pages and has no authentication of its own; this flow is interim, pending migration to Posit hosting with a DWR-scoped auth boundary.

---

## Report features

### Science Field Coverage (treemap)
- Custom SVG treemap — no external charting library
- Blue hues scale with the number of partnership initiatives per subfield; grey hatched cells have **no recorded partnerships**
- Click a category header to zoom in; hover to see back affordance (gold cue)
- Stats bar always visible: science field tags · science areas covered · subfields covered · no recorded partnerships
- Links out to the [science field taxonomy definitions](https://cadwr.app.box.com/s/bq56dj39aqzb5cc526ewcul5v5606eew)

### Organizational Network: Science ↔ Staff ↔ Division (tripartite)
- **POC self-service filter** — search your name to highlight all your partnerships
- Staff labels show `Last, F.` format with full name on hover
- Click any node to see connected science fields and divisions
- Accordion legend: How to use · Column Guide · Science Categories · Top 5 Staff · Top 5 Fields

### Organizational Network: DWR ↔ Partner Organizations (bipartite)
- Node size scales by total partnerships (degree-weighted)
- Click a node → expandable table of connected partners, colored by org type
- Click a connecting line → side-by-side entity header + flat partnership table
- Hover a table row → highlights that node in the network
- Accordion legend: How to use · Node Size · Partner Types · Top 5 Divisions · Top 5 Organizations

### Supplemental PDF
Generated with `--pdf`, three pages of uniform size:

1. **Title and introduction** — background, purpose, contact, last-updated stamp
2. **Summary dashboard** — headline figures, organization types, investment types, science fields, partnership activities
3. **Science field treemap** — with title, description, how-to-read guidance, and a clickable taxonomy link

Figures carry hover tooltips as PDF annotations. These render in Adobe Acrobat Reader; most browser PDF viewers ignore them.

### Diff banner
- Shows new / removed / updated counts after each upload
- Collapsed per-partnership cards showing before → after field changes
- Collision warnings block publishing; orphan warnings are informational
- Internal report only — the external report omits it

---

## Repo structure

```
dwr-partnerships-report/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Lint + type-check + test (Python 3.11 and 3.14)
│       └── generate-report.yml     # Report pipeline + Pages deploy
│
├── data/
│   ├── latest.csv                  # Pipeline input — git history = full audit trail
│   ├── inventory.csv               # Real 119-row inventory — GITIGNORED, local only
│   └── dwr_custom_taxonomy.csv     # Science field taxonomy (8 categories, 37 subfields)
│
├── src/
│   └── dwr_report/                 # Main Python package (src layout)
│       ├── content.py              # Shared vocabulary, report copy, external links
│       ├── ingest/
│       │   ├── loader.py           # PartnershipData class + column normalization
│       │   └── taxonomy.py         # enrich_science_fields()
│       ├── charts/
│       │   ├── theme.py            # Colors, fonts, shared chart constants
│       │   ├── summary.py          # Summary dashboard figure
│       │   ├── treemaps.py         # Browser treemap + standalone SVG renderer
│       │   └── networks.py         # network_tripartite(), network_bipartite()
│       └── pipeline/
│           ├── diff.py             # ID watchdog + change detection
│           ├── generate_report.py  # Orchestrator: data → charts → HTML report
│           ├── export_pdf.py       # 3-page supplemental PDF with annotations
│           └── create_issue.py     # GitHub Issue changelog on each upload
│
├── templates/
│   ├── report.html                 # Jinja2: main report page (header, nav, layout)
│   ├── summary_dashboard.html      # Jinja2: summary dashboard SVG
│   ├── treemap_coverage.html       # Custom SVG treemap (squarified layout)
│   ├── network_tripartite.html     # Jinja2 + vis.js: Science ↔ Staff ↔ Division
│   └── network_bipartite.html      # Jinja2 + vis.js: Division ↔ Partner Organization
│
├── tests/                          # 182 tests, ~92% coverage
│   ├── test_content.py             # Vocabulary guards
│   ├── test_export_pdf.py          # PDF structure, annotations, review fixes
│   ├── test_treemaps.py            # Layout + terminology guards
│   ├── test_networks.py
│   ├── test_generate_report.py
│   ├── test_create_issue.py
│   ├── test_diff.py
│   ├── test_loader.py
│   └── test_taxonomy.py
│
├── upload-ui/
│   └── index.html                  # Drag-and-drop CSV uploader (GitHub Contents API)
│
├── pyproject.toml                  # ruff · mypy · pytest · setuptools
└── SETUP.md                        # First-time configuration guide
```

---

## For developers

Full instructions are in **[SETUP.md](SETUP.md)**. The short version:

```bash
git clone git@github.com-fergDWR:ferg-dwr/dwr-partnerships-report.git
cd dwr-partnerships-report
sudo apt-get install -y libcairo2      # needed for PDF export
pip install -e ".[dev,pdf]"
```

### Running checks locally

```bash
ruff format --check src/ tests/
ruff check src/ tests/
mypy                                   # paths come from pyproject.toml
pytest                                 # runs with coverage via addopts
```

### Running the report locally

```bash
mkdir -p reports
echo '{"new_ids":[],"removed_ids":[],"changed_rows":[],"warnings":[]}' > reports/diff.json

python -m dwr_report.pipeline.generate_report \
  --csv data/latest.csv \
  --diff reports/diff.json \
  --output reports/index.html \
  --taxonomy data/dwr_custom_taxonomy.csv \
  --pdf

cd reports && python -m http.server 8000
```

> Hard-refresh (`Ctrl+Shift+R` / `Cmd+Shift+R`) after regenerating to bypass browser cache.

Swap in `--csv data/inventory.csv` for a realistic render — the treemap and network layouts behave differently at 119 rows than at 5. That file is gitignored and must stay that way; it contains partner email addresses and named DWR staff.

### Expanding the taxonomy

Edit `data/dwr_custom_taxonomy.csv` to add new science categories or fields. The treemap layout recalculates automatically — no code changes needed.

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

Feature branches merge into `develop`; `develop` merges into `main` via PR, which is where CI runs as a gate. Merging into `develop` does **not** republish the site.

---