"""Read a Blender character file and emit its rig inventory as JSON.

Run with: blender --background --factory-startup --python inspect_avatar.py -- AVATAR OUTPUT
The source .blend is opened for inspection only and is never saved.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


def _vector(value):
    return [float(component) for component in value]


def _action_name(animation_data):
    action = getattr(animation_data, "action", None)
    return action.name if action is not None else None


def _action_channels(action):
    """Summarize both legacy and layered Actions without editing them."""
    curves = []
    if getattr(action, "is_action_layered", False):
        for layer in action.layers:
            for strip in layer.strips:
                for channelbag in strip.channelbags:
                    curves.extend(channelbag.fcurves)
    else:
        curves.extend(action.fcurves)
    paths = sorted({curve.data_path for curve in curves})
    return {"curve_count": len(curves), "paths": paths}


def collect_inventory(bpy):
    scene = bpy.context.scene
    armatures = []
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    mesh_inventory = sorted([{
        "name": mesh.name,
        "parent": mesh.parent.name if mesh.parent else None,
        "armature_modifiers": [
            modifier.object.name if modifier.object else None
            for modifier in mesh.modifiers if modifier.type == "ARMATURE"
        ],
        "vertex_groups": sorted(group.name for group in mesh.vertex_groups),
    } for mesh in meshes], key=lambda item: item["name"])
    for obj in bpy.data.objects:
        if obj.type != "ARMATURE":
            continue
        driven_meshes = sorted({
            mesh.name for mesh in meshes
            if any(modifier.type == "ARMATURE" and modifier.object == obj for modifier in mesh.modifiers)
            or mesh.parent == obj
        })
        bones = [{
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else None,
            "deform": bool(bone.use_deform),
            "head": _vector(bone.head_local),
            "tail": _vector(bone.tail_local),
            "matrix_local": [_vector(row) for row in bone.matrix_local],
        } for bone in obj.data.bones]
        constraints = [{
            "bone": pose_bone.name,
            "items": [{"name": item.name, "type": item.type} for item in pose_bone.constraints],
        } for pose_bone in obj.pose.bones if pose_bone.constraints]
        animation_data = obj.animation_data
        nla_actions = sorted({
            strip.action.name
            for track in animation_data.nla_tracks
            for strip in track.strips
            if strip.action is not None
        }) if animation_data is not None else []
        armatures.append({
            "name": obj.name,
            "data_name": obj.data.name,
            "linked_meshes": driven_meshes,
            "bones": bones,
            "pose_constraints": constraints,
            "active_action": _action_name(animation_data),
            "nla_actions": nla_actions,
            "object_scale": _vector(obj.scale),
            "object_matrix": [_vector(row) for row in obj.matrix_world],
        })
    armatures.sort(key=lambda item: item["name"])
    candidates = [item["name"] for item in armatures if item["linked_meshes"]]
    return {
        "schema_version": "1.0",
        "blender_version": bpy.app.version_string,
        "scene": scene.name,
        "camera": scene.camera.name if scene.camera else None,
        "render_engine": scene.render.engine,
        "render_resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "fps": scene.render.fps,
        "fps_base": scene.render.fps_base,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "unit_system": scene.unit_settings.system,
        "scale_length": scene.unit_settings.scale_length,
        "armatures": armatures,
        "meshes": mesh_inventory,
        "candidate_rigs": candidates,
        "actions": sorted([{
            "name": action.name,
            "frame_range": _vector(action.frame_range),
            "users": action.users,
            **_action_channels(action),
        } for action in bpy.data.actions], key=lambda item: item["name"]),
        "linked_libraries": sorted(library.filepath for library in bpy.data.libraries),
    }


def main(argv):
    if "--" not in argv or len(argv[argv.index("--") + 1:]) != 2:
        raise ValueError("Expected: -- AVATAR OUTPUT")
    avatar, output = (Path(value).resolve() for value in argv[argv.index("--") + 1:])
    if not avatar.is_file() or avatar.suffix.lower() != ".blend":
        raise ValueError(f"Avatar .blend not found: {avatar}")
    import bpy
    bpy.ops.wm.open_mainfile(filepath=str(avatar), load_ui=False)
    inventory = collect_inventory(bpy)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception as error:
        print(f"Avatar inventory failed: {error}", file=sys.stderr)
        raise SystemExit(1)
