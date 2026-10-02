"""Verify every baked frame in a fresh Blender process without loading CP2."""
import json
import math
from pathlib import Path
import sys
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retarget_hands import action_digest


def main(path, reopen=False):
    job = json.loads(path.read_text(encoding="utf-8"))
    expected = json.loads((path.parent / "retarget-result.json").read_text(encoding="utf-8"))
    filename = "animation.blend" if reopen else "retargeted.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path.parent / filename), load_ui=False)
    scene = bpy.context.scene
    target = bpy.data.objects[job["mapping"]["target"]["armature"]]
    if bpy.data.libraries or any(b.constraints for b in target.pose.bones):
        raise ValueError("The baked rig must not depend on external libraries or transfer constraints")
    if len([o for o in bpy.data.objects if o.type == "ARMATURE"]) != 1:
        raise ValueError("Unexpected source rig in delivery")
    if (scene.frame_start != expected["frame_start"] or scene.frame_end != expected["frame_end"]
            or scene.render.fps != expected["fps"] or abs(scene.render.fps_base - expected["fps_base"]) > 1e-7):
        raise ValueError("Baked timing differs from CP2")
    action = target.animation_data.action
    if action is None or action.name != expected["action"]:
        raise ValueError("Baked Action is missing")
    for name, digest in expected["preserved_actions"].items():
        if name not in bpy.data.actions or action_digest(bpy.data.actions[name]) != digest:
            raise ValueError(f"Manual Action changed: {name}")
    curves = [c for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves]
    if len(curves) != expected["bone_count"] * 10:
        raise ValueError("Incomplete baked bone channels")
    frame_count = scene.frame_end - scene.frame_start + 1
    if any(len(c.keyframe_points) != frame_count for c in curves):
        raise ValueError("Incomplete baked keyframes")
    if any(not math.isfinite(v) for c in curves for k in c.keyframe_points for v in k.co):
        raise ValueError("Non-finite baked channels")
    maximum = 0.0
    for frame, bones in expected["samples"].items():
        scene.frame_set(int(frame))
        rig = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for name, matrix in bones.items():
            actual = rig.pose.bones[name].matrix
            for i in range(4):
                for j in range(4):
                    value = actual[i][j]
                    if not math.isfinite(value):
                        raise ValueError("Non-finite reopened pose")
                    maximum = max(maximum, abs(value - matrix[i][j]))
    if maximum > 1e-4:
        raise ValueError(f"Baked motion differs after reopening: {maximum}")
    if not reopen:
        scene.frame_set(scene.frame_start)
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(path.parent / "animation.blend"), compress=True)
    report = {"status": "pass", "file": filename, "frame_count": frame_count,
              "action": action.name, "curve_count": len(curves),
              "keyframe_count": sum(len(c.keyframe_points) for c in curves),
              "max_transform_difference": maximum, "source_rig_loaded": False,
              "manual_actions_preserved": len(expected["preserved_actions"]), "linked_libraries": []}
    (path.parent / ("reopen-check.json" if reopen else "bake-check.json")).write_text(
        json.dumps(report, allow_nan=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    main(Path(args[0]).resolve(), "--reopen" in args)
