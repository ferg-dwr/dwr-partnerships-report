# conftest.py — shared pytest fixtures.
# Import paths are configured via `pythonpath = ["src"]` in pyproject.toml.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
