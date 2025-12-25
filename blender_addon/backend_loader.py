from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import sys
import tempfile
import zipfile
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


def _default_cache_dir() -> Path:
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "andosim_artezbuild" / "wheels"
    return Path.home() / ".cache" / "andosim_artezbuild" / "wheels"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_wheel_to_dir(wheel: Path) -> Path:
    """Extract wheel zip to a filesystem directory and return that directory.

    Note: native extension modules (e.g. *.so) cannot be imported from a wheel
    zip directly via zipimport; they must exist as real files.
    """

    wheel_hash = _sha256_file(wheel)[:16]
    target_dir = _default_cache_dir() / f"{wheel.stem}-{wheel_hash}"
    marker = target_dir / ".extracted"

    if marker.exists():
        return target_dir

    try:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"{wheel.stem}-", dir=str(target_dir.parent)))
        try:
            with zipfile.ZipFile(wheel, "r") as zf:
                zf.extractall(tmp_dir)
            (tmp_dir / ".extracted").write_text(wheel.name + "\n", encoding="utf-8")

            if target_dir.exists():
                # Replace an existing partial/old extraction.
                shutil.rmtree(target_dir, ignore_errors=True)

            tmp_dir.rename(target_dir)
            return target_dir
        finally:
            if tmp_dir.exists() and tmp_dir != target_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        # Last-resort fallback (still works in most cases, but may re-extract every run).
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"{wheel.stem}-"))
        with zipfile.ZipFile(wheel, "r") as zf:
            zf.extractall(tmp_dir)
        return tmp_dir


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
            extracted_dir = _extract_wheel_to_dir(selected)
            extracted_str = str(extracted_dir)
            if extracted_str not in sys.path:
                sys.path.insert(0, extracted_str)
            try:
                return importlib.import_module("ppf_cts_backend")
            except Exception as second_exc:
                py = sys.version_info
                raise RuntimeError(
                    "Failed to import ppf_cts_backend even after adding bundled wheel "
                    f"({selected.name}) for Blender Python {py.major}.{py.minor} ({_python_tag()}). "
                    f"Tried extracted wheel dir: {extracted_dir}"
                ) from second_exc

        py = sys.version_info
        available = ", ".join(w.name for w in wheels) if wheels else "(none found)"
        raise RuntimeError(
            "ppf_cts_backend is not available. "
            f"Blender Python is {py.major}.{py.minor} ({_python_tag()}); "
            f"available bundled wheels: {available}."
        ) from first_exc
