"""
Shared pytest fixtures and path setup for user-service unit tests.

Sets PORT before any app import (config.py reads PORT at module level),
and adds the repo root to sys.path so that contracts.validator is importable.
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment — must be set before any app.* import.
# ---------------------------------------------------------------------------
os.environ.setdefault("PORT", "5001")
os.environ.setdefault("STORAGE_BACKEND", "memory")

# ---------------------------------------------------------------------------
# sys.path — repo root so `from contracts.validator import ...` works.
# The file lives at:
#   <repo_root>/services/user-service/tests/unit/conftest.py
# so parents[4] is <repo_root>.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
