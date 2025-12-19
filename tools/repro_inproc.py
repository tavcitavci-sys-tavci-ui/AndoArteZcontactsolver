import glob
import os
import sys
import tempfile
import zipfile

ADDON = "/home/moritz/repos/artezbuild_0.0.06/blender_addon"
SCENE = os.environ.get(
    "PPF_SCENE_PATH",
    "/home/moritz/.local/share/ppf-cts/git-main/blender-test/session",
)
OUTDIR = os.environ.get(
    "PPF_OUTPUT_DIR",
    "/home/moritz/.local/share/ppf-cts/git-main/blender-test/session/output",
)

wheels = glob.glob(f"{ADDON}/wheels/ppf_cts_backend-0.0.1-*.whl")
if not wheels:
    raise RuntimeError("No wheel found in blender_addon/wheels")
wheel = wheels[0]

td = tempfile.mkdtemp(prefix="ppf_whl_")
zipfile.ZipFile(wheel).extractall(td)
sys.path.insert(0, td)

import ppf_cts_backend  # noqa: E402

print("creating session...")
s = ppf_cts_backend.Session(SCENE, OUTDIR)
print("stepping...")
out = s.step([])
print("OK", len(out), out[:6])
