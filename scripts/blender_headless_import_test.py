import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from blender_addon import backend_loader
from blender_addon import ppf_export

# Compiled extension modules (.so) cannot be imported directly from inside a wheel zip.
# Use the same extraction/import logic the addon uses.
backend_loader.ensure_backend_importable()
ppf_cts_backend = backend_loader.import_backend()

print("ppf_cts_backend.__version__:", ppf_cts_backend.__version__)

# Build a minimal scene and export it so Session() has a valid scene_path.
import bpy

bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.mesh.primitive_grid_add(size=1.0, x_subdivisions=4, y_subdivisions=4, location=(0.0, 0.0, 2.0))
obj = bpy.context.active_object
obj.name = "Cloth"

# Register properties (best-effort) and tag as deformable.
try:
    import blender_addon

    blender_addon.register()
except Exception:
    pass

obj.artezbuild_ppf.enabled = True
obj.artezbuild_ppf.role = "DEFORMABLE"

settings = bpy.context.scene.artezbuild_ppf
settings.auto_export = True
settings.use_selected_colliders = False
settings.dt = 1e-3
settings.solver_fps = 60.0
settings.gravity = -9.8

export = ppf_export.export_ppf_scene_from_roles(bpy.context, settings)

s = ppf_cts_backend.Session(export.scene_path, "/tmp/ppf_blender_import_test")

# Build the input buffer from the current positions.
total = 0
for _, start, count in export.deformable_slices:
    total = max(total, int(start) + int(count))

curr = [0.0] * (total * 3)
for name, start, count in export.deformable_slices:
    o = bpy.data.objects[name]
    mw = o.matrix_world
    for i, v in enumerate(o.data.vertices):
        w = mw @ v.co
        sx, sy, sz = ppf_export.blender_to_solver_xyz(float(w.x), float(w.y), float(w.z))
        j = int(start) + i
        curr[3 * j + 0] = sx
        curr[3 * j + 1] = sy
        curr[3 * j + 2] = sz

out = s.step(curr)
print("step(len=", len(curr), ") -> len(out)=", len(out), sep="")
s.close()

print("OK")
