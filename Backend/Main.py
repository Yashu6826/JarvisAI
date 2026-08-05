"""Compatibility launcher for the NEXA web application."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_project_root() -> Path:
    backend_root = Path(__file__).resolve().parent
    project_root = backend_root.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return project_root


def _restart_with_project_python(project_root: Path) -> None:
    project_python = project_root / ".venv" / "Scripts" / "python.exe"
    if not project_python.exists() or os.environ.get("NEXA_PROJECT_PYTHON") == "1":
        return
    if Path(sys.executable).resolve().as_posix().lower() == project_python.resolve().as_posix().lower():
        return
    os.environ["NEXA_PROJECT_PYTHON"] = "1"
    os.execv(str(project_python), [str(project_python), *sys.argv])


def main() -> None:
    project_root = _ensure_project_root()
    _restart_with_project_python(project_root)

    import uvicorn

    from Backend.WebApp import app as nexa_app

    uvicorn.run(nexa_app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
