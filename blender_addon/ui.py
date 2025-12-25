import bpy
import sys
from . import backend_loader


def _try_import_ppf_backend():
    try:
        return backend_loader.import_backend()
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        py = sys.version_info
        py_tag = f"cp{py.major}{py.minor}"
        return RuntimeError(f"{exc} (Blender Python is {py.major}.{py.minor} / {py_tag})")
