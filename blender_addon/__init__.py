bl_info = {
    "name": "Artezbuild PPF (In-Process)",
    "author": "Moritz",
    "version": (0, 0, 6),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Artezbuild",
    "description": "In-process PPF GPU backend integration (experimental)",
    "category": "Physics",
}

import bpy

from .operators import ARTEZBUILD_OT_ppf_run, ARTEZBUILD_OT_ppf_stop
from .object_properties import ArtezbuildPPFObjectSettings
from .properties import ArtezbuildPPFSettings
from .ui import ARTEZBUILD_PT_main

_classes = (
    ARTEZBUILD_OT_ppf_run,
    ARTEZBUILD_OT_ppf_stop,
    ArtezbuildPPFObjectSettings,
    ArtezbuildPPFSettings,
    ARTEZBUILD_PT_main,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.artezbuild_ppf = bpy.props.PointerProperty(type=ArtezbuildPPFSettings)
    bpy.types.Object.artezbuild_ppf = bpy.props.PointerProperty(type=ArtezbuildPPFObjectSettings)


def unregister():
    if hasattr(bpy.types.Scene, "artezbuild_ppf"):
        del bpy.types.Scene.artezbuild_ppf

    if hasattr(bpy.types.Object, "artezbuild_ppf"):
        del bpy.types.Object.artezbuild_ppf

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
