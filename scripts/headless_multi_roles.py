import os
import sys
import tempfile

import bpy
import mathutils


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import blender_addon
from blender_addon import backend_loader, ppf_export


def _reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)


def _tag(obj, enabled: bool, role: str):
    obj.artezbuild_ppf.enabled = bool(enabled)
    obj.artezbuild_ppf.role = role


def main():
    _reset_scene()

    # Two deformables.
    bpy.ops.mesh.primitive_grid_add(size=1.0, x_subdivisions=16, y_subdivisions=16, location=(0.0, 0.0, 2.0))
    cloth_a = bpy.context.active_object
    cloth_a.name = "ClothA"

    bpy.ops.mesh.primitive_grid_add(size=1.0, x_subdivisions=16, y_subdivisions=16, location=(0.2, 0.0, 2.5))
    cloth_b = bpy.context.active_object
    cloth_b.name = "ClothB"

    # Static collider.
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    floor.scale = (3.0, 3.0, 0.1)

    # Register addon (so properties exist).
    try:
        blender_addon.register()
    except Exception:
        # Already registered.
        pass

    _tag(cloth_a, True, "DEFORMABLE")
    _tag(cloth_b, True, "DEFORMABLE")
    _tag(floor, True, "STATIC_COLLIDER")

    settings = bpy.context.scene.artezbuild_ppf
    settings.auto_export = True
    settings.use_selected_colliders = False
    settings.dt = 1e-3
    settings.solver_fps = 60.0
    settings.gravity = -9.8

    export = ppf_export.export_ppf_scene_from_roles(bpy.context, settings)
    assert len(export.deformable_slices) == 2, export.deformable_slices

    backend = backend_loader.import_backend()
    out_dir = tempfile.mkdtemp(prefix="ppf_blender_test_")
    sess = backend.Session(export.scene_path, out_dir)

    # Build flat vertex buffer in solver coords.
    total = 0
    for _, start, count in export.deformable_slices:
        total = max(total, int(start) + int(count))

    curr = [0.0] * (total * 3)
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
    assert len(out) == len(curr), (len(out), len(curr))

    # Apply back to objects.
    for name, start, count in export.deformable_slices:
        obj = bpy.data.objects[name]
        mw_inv = obj.matrix_world.inverted_safe()
        for i, v in enumerate(obj.data.vertices):
            j = int(start) + i
            wx, wy, wz = ppf_export.solver_to_blender_xyz(
                float(out[3 * j + 0]),
                float(out[3 * j + 1]),
                float(out[3 * j + 2]),
            )
            local = mw_inv @ mathutils.Vector((wx, wy, wz))
            v.co.x = float(local.x)
            v.co.y = float(local.y)
            v.co.z = float(local.z)
        obj.data.update()
        obj.update_tag()

    sess.close()

    print("OK: multi-deformable roles export+step")


if __name__ == "__main__":
    main()
