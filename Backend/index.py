"""Vercel entrypoint for the Nexa backend.

Deploy with Vercel's Root Directory set to `Backend`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent

if "Backend" not in sys.modules:
    backend_package = types.ModuleType("Backend")
    backend_package.__path__ = [str(BACKEND_ROOT)]
    sys.modules["Backend"] = backend_package

from Backend.WebApp import app

