"""Test setup for tramat's own scripts (stdlib + PyYAML + pytest only)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
STARTER = REPO_ROOT / "examples" / "starter-lakehouse"
sys.path.insert(0, str(SCRIPTS))
