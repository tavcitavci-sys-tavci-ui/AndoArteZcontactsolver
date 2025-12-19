import os
import sys
import tempfile
import traceback

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import blender_addon
from blender_addon import backend_loader, ppf_export


def _reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)


def _ensure_registered():
    try:
        blender_addon.register()
    except Exception:
        # Already registered or running in a context where registration isn't needed.
        pass


def _tag(obj, enabled: bool, role: str):
    obj.artezbuild_ppf.enabled = bool(enabled)
    obj.artezbuild_ppf.role = role


def _mesh_stats(obj) -> dict:
    if obj is None or obj.type != "MESH":
        return {"name": getattr(obj, "name", None), "type": getattr(obj, "type", None)}

    mesh = obj.data
    depsgraph = bpy.context.evaluated_depsgraph_get()

    tri_count = None
    try:
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = obj_eval.to_mesh()
        try:
            mesh_eval.calc_loop_triangles()
            tri_count = len(getattr(mesh_eval, "loop_triangles", []) or [])
        finally:
            obj_eval.to_mesh_clear()
    except Exception:
        tri_count = None

    return {
        "name": obj.name,
        "verts": len(mesh.vertices),
        "edges": len(mesh.edges),
        "faces": len(mesh.polygons),
        "tris_eval": tri_count,
    }


def _build_scene(subdiv: int):
    # Deformable: high-poly grid.
    bpy.ops.mesh.primitive_grid_add(
        size=2.0,
        x_subdivisions=int(subdiv),
        y_subdivisions=int(subdiv),
        location=(0.0, 0.0, 2.0),
    )
    cloth = bpy.context.active_object
    cloth.name = f"Cloth_{int(subdiv)}"

    # Static collider: floor.
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    floor.scale = (4.0, 4.0, 0.1)

    # Static collider: cylinder rod.
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=64,
        radius=0.12,
        depth=5.0,
        location=(0.6, 0.0, 1.2),
        rotation=(0.0, 1.57079632679, 0.0),
    )
    rod = bpy.context.active_object
    rod.name = "Rod"

    _ensure_registered()

    _tag(cloth, True, "DEFORMABLE")
    _tag(floor, True, "STATIC_COLLIDER")
    _tag(rod, True, "STATIC_COLLIDER")

    # Recommended: keep everything in object mode.
    if cloth.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    return cloth, floor, rod


def _build_curr_from_slices(export_result):
    total = 0
    for _, start, count in export_result.deformable_slices:
        total = max(total, int(start) + int(count))

    curr = [0.0] * (total * 3)
    for name, start, count in export_result.deformable_slices:
        obj = bpy.data.objects[name]
        mw = obj.matrix_world
        # NOTE: Must match export vertex ordering/count; avoid modifiers.
        if len(obj.data.vertices) != int(count):
            raise RuntimeError(
                f"Vertex count mismatch for '{name}': obj has {len(obj.data.vertices)} but export expects {int(count)}"
            )
        for i, v in enumerate(obj.data.vertices):
            w = mw @ v.co
            sx, sy, sz = ppf_export.blender_to_solver_xyz(float(w.x), float(w.y), float(w.z))
            j = int(start) + i
            curr[3 * j + 0] = sx
            curr[3 * j + 1] = sy
            curr[3 * j + 2] = sz

    return curr


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except Exception:
        return int(default)


def main():
    # User-tunable knobs via env vars.
    start = _env_int("PPF_SUBDIV_START", 256)
    min_subdiv = _env_int("PPF_SUBDIV_MIN", 16)
    steps = _env_int("PPF_STEPS", 3)

    # Candidate list: geometric-ish decrease until min.
    candidates = []
    v = start
    while v >= min_subdiv:
        if v not in candidates:
            candidates.append(v)
        v = int(v * 0.75)
        if v == candidates[-1]:
            v -= 1

    # Ensure we hit min exactly.
    if min_subdiv not in candidates:
        candidates.append(min_subdiv)

    print("PPF headless high-poly threshold test")
    print(f"Candidates: {candidates}")
    print(f"Steps per attempt: {steps}")

    best_ok = None
    last_error = None

    for subdiv in candidates:
        print("\n=== Attempt subdiv:", subdiv, "===")
        _reset_scene()

        try:
            cloth, floor, rod = _build_scene(subdiv)

            print("Mesh stats:")
            print("  deformable:", _mesh_stats(cloth))
            print("  collider floor:", _mesh_stats(floor))
            print("  collider rod:", _mesh_stats(rod))

            settings = bpy.context.scene.artezbuild_ppf
            settings.auto_export = True
            settings.use_selected_colliders = False
            settings.dt = 1e-3
            settings.solver_fps = 60.0
            settings.gravity = -9.8

            export = ppf_export.export_ppf_scene_from_roles(bpy.context, settings)
            print("Export scene_path:", export.scene_path)
            print("Export deformables:", export.deformable_object_names)
            print("Export colliders:", export.collider_object_names)
            print("Export deformable_slices:", export.deformable_slices)
            if getattr(export, "warnings", None):
                print("Export warnings:")
                for w in export.warnings:
                    print("  -", str(w))

            backend = backend_loader.import_backend()
            out_dir = tempfile.mkdtemp(prefix="ppf_blender_highpoly_")
            print("Backend output_dir:", out_dir)

            sess = backend.Session(export.scene_path, out_dir)
            print("Session initialized: OK")

            curr = _build_curr_from_slices(export)

            for i in range(int(steps)):
                out = sess.step(curr)
                if len(out) != len(curr):
                    raise RuntimeError(f"step() returned {len(out)} floats, expected {len(curr)}")
                curr = list(out)
                print(f"Session.step {i + 1}/{steps}: OK")

            sess.close()
            print("Session closed: OK")

            best_ok = subdiv
            last_error = None
            print("SUCCESS at subdiv:", subdiv)
            break

        except Exception as exc:
            last_error = exc
            print("FAIL at subdiv:", subdiv)
            traceback.print_exc()
            # continue to next smaller

    print("\n=== Summary ===")
    if best_ok is not None:
        print("Best success subdiv:", best_ok)
    else:
        print("No successful run.")

    if last_error is not None:
        print("Last error:", repr(last_error))


if __name__ == "__main__":
    main()
