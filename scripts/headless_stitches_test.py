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


def _make_group(obj, name, predicate):
    vg = obj.vertex_groups.new(name=name)
    for v in obj.data.vertices:
        if predicate(v):
            vg.add([v.index], 1.0, "REPLACE")
    return vg


def main():
    _reset_scene()

    # Two grids close to each other.
    bpy.ops.mesh.primitive_grid_add(size=1.0, x_subdivisions=20, y_subdivisions=20, location=(0.0, 0.0, 2.0))
    a = bpy.context.active_object
    a.name = "ClothA"

    # Note: keep a tiny separation so we don't start with perfectly coincident points,
    # which can trigger a CUDA assert in upstream contact code.
    bpy.ops.mesh.primitive_grid_add(size=1.0, x_subdivisions=20, y_subdivisions=20, location=(0.0, 1.01, 2.0))
    b = bpy.context.active_object
    b.name = "ClothB"

    # Register addon so properties exist.
    try:
        blender_addon.register()
    except Exception:
        pass

    # Mark A as deformable and add a stitch source group near +Y edge.
    a.artezbuild_ppf.enabled = True
    a.artezbuild_ppf.role = "DEFORMABLE"
    _make_group(a, "PPF_STITCH", lambda v: v.co.y > 0.45)

    # Mark B as deformable and restrict stitch target edges to a band near -Y edge.
    b.artezbuild_ppf.enabled = True
    b.artezbuild_ppf.role = "DEFORMABLE"
    _make_group(b, "PPF_STITCH_TGT", lambda v: v.co.y < -0.45)

    # Configure stitch settings on A targeting B.
    a.artezbuild_ppf.stitch_enabled = True
    a.artezbuild_ppf.stitch_target_object = b
    a.artezbuild_ppf.stitch_source_vertex_group = "PPF_STITCH"
    a.artezbuild_ppf.stitch_target_vertex_group = "PPF_STITCH_TGT"
    a.artezbuild_ppf.stitch_max_distance = 0.25

    # Debug: count group vertices.
    def _count_in_group(obj, group_name):
        if group_name not in obj.vertex_groups:
            return 0
        idx = obj.vertex_groups[group_name].index
        c = 0
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group == idx and float(g.weight) > 0.0:
                    c += 1
                    break
        return c

    print("A stitch_enabled:", bool(a.artezbuild_ppf.stitch_enabled))
    print("A stitch_target:", getattr(a.artezbuild_ppf.stitch_target_object, "name", None))
    print("A src group count:", _count_in_group(a, "PPF_STITCH"))
    print("B tgt group count:", _count_in_group(b, "PPF_STITCH_TGT"))
    print("B edges:", len(b.data.edges))
    if "PPF_STITCH_TGT" in b.vertex_groups:
        tgt_idx = b.vertex_groups["PPF_STITCH_TGT"].index
        in_group = [False] * len(b.data.vertices)
        for v in b.data.vertices:
            for g in v.groups:
                if g.group == tgt_idx and float(g.weight) > 0.0:
                    in_group[int(v.index)] = True
                    break
        cand = 0
        for e in b.data.edges:
            v0, v1 = int(e.vertices[0]), int(e.vertices[1])
            if in_group[v0] and in_group[v1]:
                cand += 1
        print("B candidate edges (both in group):", cand)

    settings = bpy.context.scene.artezbuild_ppf
    settings.auto_export = True
    settings.use_selected_colliders = False
    settings.dt = 1e-3
    settings.solver_fps = 60.0
    settings.gravity = -9.8

    export = ppf_export.export_ppf_scene_from_roles(bpy.context, settings)

    with open(os.path.join(export.scene_path, "info.toml"), "r", encoding="utf-8") as f:
        info = f.read()
    print("info.toml:\n", info)

    stitch_ind_path = os.path.join(export.scene_path, "bin", "stitch_ind.bin")
    stitch_w_path = os.path.join(export.scene_path, "bin", "stitch_w.bin")
    assert os.path.exists(stitch_ind_path), stitch_ind_path
    assert os.path.exists(stitch_w_path), stitch_w_path

    # Step once.
    backend = backend_loader.import_backend()
    out_dir = tempfile.mkdtemp(prefix="ppf_blender_stitch_test_")
    sess = backend.Session(export.scene_path, out_dir)

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
    assert len(out) == len(curr)
    sess.close()

    print("OK: stitches exported and session stepped")


if __name__ == "__main__":
    main()
