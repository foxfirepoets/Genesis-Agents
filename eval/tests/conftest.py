"""Make the repo root importable so ``import eval`` resolves to this package.

Tests are deliberately plain sync functions driving coroutines through
``asyncio.run`` — no pytest-asyncio dependency, no event-loop config to drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
