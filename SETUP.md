# Setup

First-time configuration for `dwr-partnerships-report`. If you only want to
upload a CSV and get a new report, you don't need any of this — see the upload
steps in [README.md](README.md). This guide is for getting a development
environment running, or standing the pipeline up in a new repository.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python **3.11+** | CI tests against 3.11 and 3.14. `requires-python = ">=3.11"`. |
| Git | Configured with SSH access to the repo. |
| `libcairo2` | System library. Needed only for PDF export — the pip package alone is not sufficient. |
| GitHub CLI (`gh`) | Optional, but every workflow command in these docs assumes it. |

On Debian/Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y libcairo2
```

---

## 2. Clone

The repo uses an SSH host alias so it can be worked on alongside other GitHub
accounts on the same machine.

```bash
git clone git@github.com-fergDWR:ferg-dwr/dwr-partnerships-report.git
cd dwr-partnerships-report
```

If that alias isn't set up yet, add it to `~/.ssh/config`:

```
Host github.com-fergDWR
    HostName github.com
    User git
    IdentityFile ~/.ssh/dwr_id_ed25519
    IdentitiesOnly yes
```

Verify with `ssh -T git@github.com-fergDWR`.

---

## 3. Install

```bash
python -m venv .venv && source .venv/bin/activate   # or conda, if you prefer
pip install -e ".[dev,pdf]"
```

Two optional extras are defined in `pyproject.toml`:

- **`dev`** — pytest, pytest-cov, ruff, mypy, pandas-stubs
- **`pdf`** — cairosvg, pypdf (required for `--pdf` export)

### Verify the install

This project uses a `src/` layout, so a broken install fails in a confusing
way — imports resolve to nothing rather than erroring loudly. Check explicitly:

```bash
python -c "import dwr_report; print(dwr_report.__file__)"
```

You want a path ending in **`src/dwr_report/__init__.py`**. Anything else means
the editable install didn't take.

```bash
find . -name "*.egg-info" -maxdepth 4 -not -path "./.git/*"
```

Exactly **one** result, at `./src/dwr_partnerships_report.egg-info`. If you see
a second at the repo root or nested inside the package, those are stale
artifacts from an earlier layout — `pip` writes new ones but never removes old
ones. Delete them and reinstall:

```bash
rm -rf dwr_partnerships_report.egg-info src/dwr_report/*.egg-info
find . -name __pycache__ -type d -prune -exec rm -rf {} +
pip install -e ".[dev,pdf]"
```

---

## 4. Run the checks

```bash
ruff format --check src/ tests/
ruff check src/ tests/
mypy                                 # reads `files` from pyproject.toml
pytest                               # runs with coverage via addopts
```

All four should pass on a clean checkout. `mypy` takes no path argument on
purpose — the paths live in `[tool.mypy]` so there is one place to change them.

---

## 5. Generate a report locally

The pipeline needs a diff file, so create an empty one on a first run:

```bash
mkdir -p reports
echo '{"new_ids":[],"removed_ids":[],"changed_rows":[],"warnings":[]}' > reports/diff.json

python -m dwr_report.pipeline.generate_report \
  --csv data/latest.csv \
  --diff reports/diff.json \
  --output reports/index.html \
  --taxonomy data/dwr_custom_taxonomy.csv \
  --pdf
```

This writes three things into `reports/`:

| File | Contents |
|---|---|
| `index.html` | External report — published to GitHub Pages |
| `internal_report.html` | Internal report — adds the staff network and diff banner |
| `report.pdf` | 3-page supplemental report (intro, dashboard, science treemap) |

Drop `--pdf` if you haven't installed the `pdf` extra.

To view it:

```bash
cd reports && python -m http.server 8000
```

Then open <http://localhost:8000>. Hard-refresh (`Ctrl+Shift+R` /
`Cmd+Shift+R`) after regenerating — the browser caches the iframes aggressively.

### Which CSV to use

- **`data/latest.csv`** — 5 synthetic rows. What the pipeline runs on in CI.
  Safe, fast, committed.
- **`data/inventory.csv`** — the real 119-row inventory. **Gitignored.** Use it
  when you need a realistic render (the treemap and network layouts behave
  differently at scale), but it contains partner email addresses and named DWR
  staff, so it must never be committed to a public repo.

Run commands are otherwise identical; just swap the `--csv` argument.

---

## 6. Repository configuration

Only needed when standing this up in a new repo.

### GitHub Pages

Settings → Pages → **Source: GitHub Actions**. The workflow deploys via
`actions/deploy-pages`; the classic "deploy from a branch" mode will not work.

### Workflow permissions

Already declared in `.github/workflows/generate-report.yml`:

```yaml
permissions:
  contents: read      # actions/checkout
  pages: write        # deploy to Pages
  id-token: write     # OIDC verification for the deployment
  issues: write       # create changelog issues
```

Declaring any `permissions` block sets every unlisted scope to `none`, so each
one the workflow needs must appear explicitly — including `contents`, without
which `actions/checkout` fails the moment the repo becomes private.

### Branch protection

If you add required status checks on `main`, the job names are
`Lint & type-check`, `Test (Python 3.11)`, and `Test (Python 3.14)`. They only
become selectable after the workflow has run at least once on the default
branch.

### Optional: track the reports directory

`.gitignore` contains a `!reports/.gitkeep` negation, but the file itself does
not exist, so `reports/` is not tracked. Nothing depends on this (the workflow
runs `mkdir -p reports`), but if you want the directory in the repo:

```bash
touch reports/.gitkeep && git add reports/.gitkeep
```

---

## 7. Personal access token for the upload UI

The upload UI commits `data/latest.csv` through the GitHub Contents API using a
token you paste at upload time. It is never stored — it is used for the single
request and discarded.

Create one at Settings → Developer settings → Personal access tokens, with
**write access to repository contents**. Classic tokens need the `repo` scope;
fine-grained tokens need `Contents: Read and write` on this repository only.

> The upload UI is served from GitHub Pages, which has no authentication on a
> public repository. This flow is interim, pending migration to Posit hosting
> with a DWR-scoped auth boundary.

---

## 8. Development workflow

```bash
git checkout develop && git pull
git checkout -b feat/your-change
# ... work, then:
pytest
git add <specific files>            # not `git add -A` — see below
git commit -m "feat: what changed"
git push -u origin feat/your-change
gh pr create --base develop
```

Merging into `develop` runs CI. Merging `develop` into `main` runs CI **and**
regenerates the report, then deploys to Pages.

Two habits worth keeping:

**Stage files explicitly.** `data/inventory.csv` is gitignored, but a broad
`git add -A` is still how unrelated scratch files end up in commits. Name what
you mean.

**Run the workflow commands locally before pushing.** Every `run:` line in the
workflows executes verbatim from the repo root, so a failing step can almost
always be reproduced without waiting on Actions:

```bash
python -m dwr_report.pipeline.diff data/previous.csv data/latest.csv reports/diff.json
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'dwr_report'`**
The editable install didn't take. Re-run the verification in section 3.

**`python -m dwr_report.pipeline.generate_report.py` fails**
`-m` takes a dotted module name, not a file path — drop the `.py`.

**`FileNotFoundError: data/previous.csv`**
That file is generated during the Actions run. To reproduce locally:
`git show HEAD~1:data/latest.csv > data/previous.csv`

**PDF export raises on `import cairosvg`**
Install the system library (`sudo apt-get install -y libcairo2`) — the pip
package links against it and won't import without it.

**A test asserts on extracted PDF text and fails after a dependency bump**
pypdf infers word spacing from glyph positions and the heuristic changed
between 5.x and 6.x. `tests/test_export_pdf.py` normalises whitespace before
comparing for exactly this reason; keep new assertions doing the same.

**Templates not found when running from another directory**
Template paths are resolved relative to the current working directory, so both
`pytest` and the pipeline must be run from the repository root.