from __future__ import annotations

import importlib.util
import ctypes
import sys


def _missing_message(package: str) -> str:
    return (
        f"Missing dependency: {package}\n"
        "Install desktop pet dependencies with:\n"
        "  python -m pip install -r requirements.txt"
    )


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> int:
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.")
        return 2

    if not _has_module("PySide6"):
        print(_missing_message("PySide6"))
        return 2

    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ExamPlanner.StudyPet")
        except Exception:
            pass

    try:
        from .ui import run_app
    except Exception as exc:  # pragma: no cover - user-facing bootstrap guard
        print(f"Desktop pet failed to load: {exc}")
        return 1

    return run_app(smoke_test="--smoke-test" in sys.argv)
