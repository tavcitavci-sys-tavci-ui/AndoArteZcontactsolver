import importlib
import os
import sys
import zipfile
from pathlib import Path

import bpy


def _addon_root() -> Path:
    return Path(__file__).resolve().parent


def _find_wheel() -> Path:
    wheels_dir = _addon_root() / "wheels"
    if not wheels_dir.exists():
        raise FileNotFoundError(f"Missing wheels dir: {wheels_dir}")

    # Prefer cp311 wheels (Blender 4.x bundles Python 3.11).
    wheels = sorted(wheels_dir.glob("*.whl"))
    if not wheels:
        raise FileNotFoundError(f"No wheel found in: {wheels_dir}")

    cp311 = [w for w in wheels if "cp311" in w.name]
    return cp311[0] if cp311 else wheels[0]


def _extract_root() -> Path:
    # Linux-only addon: use ~/.cache by default.
    base = Path(os.path.expanduser("~/.cache/artezbuild_ppf"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def ensure_backend_importable() -> None:
    wheel = _find_wheel()
    dest = _extract_root() / (wheel.stem)
    marker = dest / ".extracted"

    wheel_mtime = int(wheel.stat().st_mtime)
    needs_extract = True
    if marker.exists():
        try:
            recorded = int(marker.read_text(encoding="utf-8").strip() or "0")
            needs_extract = recorded != wheel_mtime
        except Exception:
            needs_extract = True

    if needs_extract:
        if dest.exists():
            # Best-effort cleanup; ignore failures.
            try:
                for p in dest.rglob("*"):
                    if p.is_file() or p.is_symlink():
                        try:
                            p.unlink()
                        except Exception:
                            pass
                for p in sorted(dest.rglob("*"), reverse=True):
                    if p.is_dir():
                        try:
                            p.rmdir()
                        except Exception:
                            pass
            except Exception:
                pass

        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(wheel, "r") as zf:
            zf.extractall(dest)
        marker.write_text(str(wheel_mtime), encoding="utf-8")

    # Put extraction dir first to avoid shadowing by workspace folders.
    dest_str = str(dest)
    if dest_str in sys.path:
        sys.path.remove(dest_str)
    sys.path.insert(0, dest_str)


def import_backend():
    ensure_backend_importable()

    # If something already imported a wrong module (e.g. a source folder), force reload.
    mod = sys.modules.get("ppf_cts_backend")
    if mod is not None and not hasattr(mod, "Session"):
        del sys.modules["ppf_cts_backend"]

    return importlib.import_module("ppf_cts_backend")
