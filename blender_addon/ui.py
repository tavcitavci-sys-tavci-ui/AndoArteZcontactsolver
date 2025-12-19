import bpy

from . import backend_loader


class ARTEZBUILD_PT_main(bpy.types.Panel):
    bl_label = "Artezbuild PPF"
    bl_idname = "ARTEZBUILD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Artezbuild"

    def draw(self, context):
        layout = self.layout
        layout.label(text="In-process PPF (stub)")
        row = layout.row(align=True)
        row.operator("artezbuild.ppf_run", text="Run")
        row.operator("artezbuild.ppf_stop", text="Stop")

        col = layout.column(align=True)
        col.label(text="Backend module:")
        try:
            backend = backend_loader.import_backend()
            col.label(text=f"ppf_cts_backend OK: {backend.__version__}")
        except Exception as exc:
            col.label(text=f"missing: {exc}")

        settings = getattr(context.scene, "artezbuild_ppf", None)
        if settings is None:
            layout.label(text="Settings: not initialized")
            return

        obj = context.active_object
        if obj is not None and obj.type == "MESH" and hasattr(obj, "artezbuild_ppf"):
            box = layout.box()
            box.label(text="Active Object")
            box.prop(obj.artezbuild_ppf, "enabled")
            row = box.row(align=True)
            row.enabled = bool(obj.artezbuild_ppf.enabled)
            row.prop(obj.artezbuild_ppf, "role", text="Role")

            row = box.row(align=True)
            row.enabled = bool(obj.artezbuild_ppf.enabled)
            row.prop(obj.artezbuild_ppf, "use_object_params")

            if bool(obj.artezbuild_ppf.enabled) and bool(obj.artezbuild_ppf.use_object_params):
                if obj.artezbuild_ppf.role == "DEFORMABLE":
                    col = box.column(align=True)
                    col.label(text="Shell (per-object)")
                    col.prop(obj.artezbuild_ppf, "tri_model")
                    col.prop(obj.artezbuild_ppf, "tri_density")
                    col.prop(obj.artezbuild_ppf, "tri_young_mod")
                    col.prop(obj.artezbuild_ppf, "tri_poiss_rat")
                    col.prop(obj.artezbuild_ppf, "tri_bend")
                    col.prop(obj.artezbuild_ppf, "tri_shrink")
                    col.prop(obj.artezbuild_ppf, "tri_contact_gap")
                    col.prop(obj.artezbuild_ppf, "tri_contact_offset")
                    col.prop(obj.artezbuild_ppf, "tri_strain_limit")
                    col.prop(obj.artezbuild_ppf, "tri_friction")
                elif obj.artezbuild_ppf.role == "STATIC_COLLIDER":
                    col = box.column(align=True)
                    col.label(text="Static Collider (per-object)")
                    col.prop(obj.artezbuild_ppf, "static_contact_gap")
                    col.prop(obj.artezbuild_ppf, "static_contact_offset")
                    col.prop(obj.artezbuild_ppf, "static_friction")

            if bool(obj.artezbuild_ppf.enabled) and obj.artezbuild_ppf.role == "DEFORMABLE":
                col = box.column(align=True)
                col.label(text="Pins")
                col.prop(obj.artezbuild_ppf, "pin_enabled")
                row = col.row(align=True)
                row.enabled = bool(obj.artezbuild_ppf.pin_enabled)
                row.prop(obj.artezbuild_ppf, "pin_vertex_group")
                row = col.row(align=True)
                row.enabled = bool(obj.artezbuild_ppf.pin_enabled)
                row.prop(obj.artezbuild_ppf, "pin_pull_strength")

                col = box.column(align=True)
                col.label(text="Stitches")
                col.prop(obj.artezbuild_ppf, "stitch_enabled")
                row = col.row(align=True)
                row.enabled = bool(obj.artezbuild_ppf.stitch_enabled)
                row.prop(obj.artezbuild_ppf, "stitch_target_object")
                row = col.row(align=True)
                row.enabled = bool(obj.artezbuild_ppf.stitch_enabled)
                row.prop(obj.artezbuild_ppf, "stitch_source_vertex_group")
                row = col.row(align=True)
                row.enabled = bool(obj.artezbuild_ppf.stitch_enabled)
                row.prop(obj.artezbuild_ppf, "stitch_target_vertex_group")
                row = col.row(align=True)
                row.enabled = bool(obj.artezbuild_ppf.stitch_enabled)
                row.prop(obj.artezbuild_ppf, "stitch_max_distance")

        col = layout.column(align=True)
        col.prop(settings, "auto_export")
        col.prop(settings, "use_selected_colliders")
        col.prop(settings, "scene_path")
        col.prop(settings, "output_dir")
        col.prop(settings, "target_object")
        col.prop(settings, "fps")

        box = layout.box()
        box.label(text="Solver")
        box.prop(settings, "dt")
        box.prop(settings, "solver_fps")
        box.prop(settings, "gravity")

        box = layout.box()
        box.label(text="Shell Material")
        box.prop(settings, "tri_model")
        box.prop(settings, "tri_density")
        box.prop(settings, "tri_young_mod")
        box.prop(settings, "tri_poiss_rat")
        box.prop(settings, "tri_bend")
        box.prop(settings, "tri_shrink")
        box.prop(settings, "tri_contact_gap")
        box.prop(settings, "tri_contact_offset")
        box.prop(settings, "tri_strain_limit")
        box.prop(settings, "tri_friction")

        box = layout.box()
        box.label(text="Static Collider")
        box.prop(settings, "static_contact_gap")
        box.prop(settings, "static_contact_offset")
        box.prop(settings, "static_friction")

        layout.separator()

        row = layout.row(align=True)
        if bool(settings.running):
            row.enabled = False
        row.operator("artezbuild.ppf_run", text="Run", icon="PLAY")

        row = layout.row(align=True)
        if not bool(settings.running):
            row.enabled = False
        row.operator("artezbuild.ppf_stop", text="Stop", icon="PAUSE")
