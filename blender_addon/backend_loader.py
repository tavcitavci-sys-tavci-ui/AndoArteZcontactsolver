from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _addon_dir() -> Path:
    return Path(__file__).resolve().parent


def _wheels_dir() -> Path:
    return _addon_dir() / "wheels"


def _python_tag() -> str:
    py = sys.version_info
    return f"cp{py.major}{py.minor}"


def _candidate_wheels() -> list[Path]:
    wheels_dir = _wheels_dir()
    if not wheels_dir.exists() or not wheels_dir.is_dir():
        return []
    return sorted(wheels_dir.glob("ppf_cts_backend-*.whl"))


def _select_wheel_for_runtime(wheels: list[Path]) -> Path | None:
    tag = _python_tag()

    # Prefer an exact CPython tag match.
    for wheel in wheels:
        if f"-{tag}-" in wheel.name:
            return wheel

    return None


def import_backend():
    """Import and return the native PPF backend.

    Strategy:
    1) Try a normal import (works when Blender Extensions installed wheels).
    2) If missing, add a matching bundled wheel (./wheels/*.whl) to sys.path and retry.
    """

    try:
        return importlib.import_module("ppf_cts_backend")
    except Exception as first_exc:
        wheels = _candidate_wheels()
        selected = _select_wheel_for_runtime(wheels)
        if selected is not None:
            selected_str = str(selected)
            if selected_str not in sys.path:
                sys.path.insert(0, selected_str)
            try:
                return importlib.import_module("ppf_cts_backend")
            except Exception as second_exc:
                py = sys.version_info
                raise RuntimeError(
                    "Failed to import ppf_cts_backend even after adding bundled wheel "
                    f"({selected.name}) for Blender Python {py.major}.{py.minor} ({_python_tag()})."
                ) from second_exc

        py = sys.version_info
        available = ", ".join(w.name for w in wheels) if wheels else "(none found)"
        raise RuntimeError(
            "ppf_cts_backend is not available. "
            f"Blender Python is {py.major}.{py.minor} ({_python_tag()}); "
            f"available bundled wheels: {available}."
        ) from first_exc
