import os
import sys
import tempfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import blender_addon
from blender_addon import backend_loader, ppf_export


def _reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)


def main():
    _reset_scene()

    bpy.ops.mesh.primitive_grid_add(size=1.0, x_subdivisions=16, y_subdivisions=16, location=(0.0, 0.0, 2.0))
    cloth = bpy.context.active_object
    cloth.name = "Cloth"

    # Register addon so properties exist.
    try:
        blender_addon.register()
    except Exception:
        pass

    # Create a pin vertex group and assign top row (approx) to it.
    vg = cloth.vertex_groups.new(name="PPF_PIN")
    for v in cloth.data.vertices:
        # Pin vertices with higher Z in local coords (grid is in XY plane, so use Y as proxy after object location)
        # In this simple grid, use local y > 0.4 to pin a strip.
        if v.co.y > 0.4:
            vg.add([v.index], 1.0, "REPLACE")

    cloth.artezbuild_ppf.enabled = True
    cloth.artezbuild_ppf.role = "DEFORMABLE"
    cloth.artezbuild_ppf.pin_enabled = True
    cloth.artezbuild_ppf.pin_vertex_group = "PPF_PIN"
    cloth.artezbuild_ppf.pin_pull_strength = 0.0  # fixed pins

    settings = bpy.context.scene.artezbuild_ppf
    settings.auto_export = True
    settings.use_selected_colliders = False
    settings.dt = 1e-3
    settings.solver_fps = 60.0
    settings.gravity = -9.8

    export = ppf_export.export_ppf_scene_from_roles(bpy.context, settings)

    # Verify pin block files exist.
    assert os.path.exists(os.path.join(export.scene_path, "bin", "pin-ind-0.bin"))

    backend = backend_loader.import_backend()
    out_dir = tempfile.mkdtemp(prefix="ppf_blender_pins_test_")
    sess = backend.Session(export.scene_path, out_dir)

    total = 0
    for _, start, count in export.deformable_slices:
        total = max(total, int(start) + int(count))

    curr = [0.0] * (total * 3)
    # Start from the current positions.
    for name, start, count in export.deformable_slices:
        obj = bpy.data.objects[name]
        mw = obj.matrix_world
        for i, v in enumerate(obj.data.vertices):
            w = mw @ v.co
            sx, sy, sz = ppf_export.blender_to_solver_xyz(float(w.x), float(w.y), float(w.z))
            j = int(start) + i
            curr[3 * j + 0] = sx
            curr[3 * j + 1] = sy
            curr[3 * j + 2] = sz

    out = sess.step(curr)
    assert len(out) == len(curr)

    sess.close()

    print("OK: pins exported and session stepped")


if __name__ == "__main__":
    main()
