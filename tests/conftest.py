# conftest.py — shared pytest fixtures and path setup

import sys
from pathlib import Path

# Make sure `src/` is importable from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))
