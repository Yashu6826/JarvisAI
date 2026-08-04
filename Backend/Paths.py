"""Filesystem paths shared by the backend.

Vercel deployments have a read-only project directory. Runtime files that may
be written during requests must live under /tmp there.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
_default_runtime_root = Path(tempfile.gettempdir()) / "nexa" if os.getenv("VERCEL") else PACKAGE_ROOT
RUNTIME_ROOT = Path(os.getenv("NEXA_RUNTIME_ROOT", str(_default_runtime_root)))
DATA_DIR = RUNTIME_ROOT / "Data"
LOG_DIR = RUNTIME_ROOT / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
