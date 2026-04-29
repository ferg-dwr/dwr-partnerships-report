# DWR Partnerships Report

[![CI](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/ci.yml/badge.svg)](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/ci.yml)
[![Report](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/generate-report.yml/badge.svg)](https://github.com/ferg-dwr/dwr-partnerships-report/actions/workflows/generate-report.yml)

Automated report generation for DWR partnership data exported from Microsoft Lists.
Upload a CSV → GitHub Actions diffs the data, flags anomalies, and publishes an updated report to GitHub Pages.

**[View the live report →](https://ferg-dwr.github.io/dwr-partnerships-report/)**

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
    │     ├── Partnerships by Science & Technology Field (treemap)
    │     ├── Science Field Coverage Gap (treemap)
    │     ├── Science Field ↔ Staff ↔ Division (network)
    │     └── Division ↔ Partner Organization (network)
    └── Publishes to GitHub Pages
```

---

## For users: uploading new data

1. Export your partnerships list from Microsoft Lists as a CSV
2. Go to the **[Upload UI](https://ferg-dwr.github.io/dwr-partnerships-report/upload-ui/)**
3. Drag and drop your CSV, enter your GitHub token, and click Upload
4. Check the **[Actions tab](https://github.com/ferg-dwr/dwr-partnerships-report/actions)** — report regenerates in ~2 minutes
5. View the updated report at **[ferg-dwr.github.io/dwr-partnerships-report](https://ferg-dwr.github.io/dwr-partnerships-report/)**

> The upload UI never stores your token. It is used once to commit the file and then discarded.

---

## Repo structure

```
dwr-partnerships-report/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Lint, type-check, test on every push/PR
│       └── generate-report.yml     # Report pipeline (triggers on data/latest.csv change)
│
├── data/
│   ├── latest.csv                  # Current dataset — git history = full audit trail
│   └── dwr_custom_taxonomy.csv     # Science field taxonomy for coverage analysis
│
├── dwr_report/                     # Main Python package
│   ├── __init__.py                 # Public API — import anything from here
│   ├── ingest/
│   │   ├── loader.py               # PartnershipData class + normalization
│   │   └── taxonomy.py             # load_taxonomy(), enrich_science_fields()
│   ├── charts/
│   │   ├── treemaps.py             # treemap(), treemap_coverage()
│   │   └── networks.py             # network_tripartite(), network_bipartite(), save_html()
│   ├── pipeline/
│   │   ├── diff.py                 # ID watchdog + change detection
│   │   └── generate_report.py      # Orchestration: loads data → charts → HTML report
│   └── utils/                      # Shared helpers (future use)
│
├── templates/
│   ├── network_tripartite.html     # Jinja2 template: Science Field ↔ Staff ↔ Division
│   └── network_bipartite.html      # Jinja2 template: Division ↔ Partner Organization
│
├── tests/
│   ├── test_diff.py                # ID watchdog + diff logic (28 tests)
│   ├── test_loader.py              # Data loading and normalization (27 tests)
│   ├── test_taxonomy.py            # Taxonomy enrichment (11 tests)
│   ├── test_treemaps.py            # Plotly treemap charts (9 tests)
│   └── test_networks.py            # vis.js network charts (15 tests)
│
├── upload-ui/
│   └── index.html                  # Drag-and-drop CSV uploader (no Git required)
│
├── reports/                        # Auto-generated HTML (committed by Actions only)
├── pyproject.toml                  # Project config: ruff, mypy, pytest, setuptools
├── SETUP.md                        # First-time configuration guide
└── .env.example                    # Environment variable template
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

All three are enforced by CI on every push and pull request.

### Running the report locally

```bash
# Create a dummy diff file if needed
echo '{"new_ids":[],"removed_ids":[],"changed_rows":[],"warnings":[]}' > reports/diff.json

# Generate the full report
python dwr_report/pipeline/generate_report.py \
  --csv data/latest.csv \
  --diff reports/diff.json \
  --output reports/index.html \
  --taxonomy data/dwr_custom_taxonomy.csv
```

### Using the package in notebooks

```python
from dwr_report import (
    PartnershipData,
    enrich_science_fields,
    treemap,
    treemap_coverage,
    network_tripartite,
    network_bipartite,
)

data = PartnershipData("data/latest.csv")
enrich_science_fields(data, "data/dwr_custom_taxonomy.csv")

fig = treemap_coverage(data, "data/dwr_custom_taxonomy.csv")
fig.show()
```

---

## ID watchdog

The diff engine compares each new CSV upload against the previous version and flags two categories of anomaly:

| Warning type | What it means | Action |
|---|---|---|
| **Orphan** | An ID in the previous data is missing from the upload | Verify the partnership was intentionally deleted in Microsoft Lists |
| **Collision** | A shared ID has a significantly different organization name | Possible ID reuse — check Microsoft Lists before publishing |

Orphan warnings are informational and do not block publishing. Collision warnings cause the Actions workflow to exit with code 2 and block the report from publishing until resolved.

---

## Branch strategy

- **`develop`** — active development; CI runs on every push
- **`main`** — production; merges from develop trigger report generation and Pages deployment
- Pull requests should target `main` from `develop`

---

## First-time setup

See **[SETUP.md](SETUP.md)** for step-by-step instructions on creating the repo, configuring the GitHub PAT secret, enabling Pages, and seeding the initial CSV.