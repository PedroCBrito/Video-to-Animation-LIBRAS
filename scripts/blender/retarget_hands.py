"""Transfer evaluated CP2 directions to the existing hand rig; run inside Blender."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import bpy
from mathutils import Matrix, Vector


def action_digest(action):
    curves = [c for layer in action.layers for strip in layer.strips
              for bag in strip.channelbags for c in bag.fcurves] if action.is_action_layered else list(action.fcurves)
    data = [(c.data_path, c.array_index, [(list(k.co), k.interpolation, list(k.handle_left), list(k.handle_right))
                                        for k in c.keyframe_points]) for c in curves]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def palm_basis(center, index, pinky):
    across = index - pinky
    along = (index + pinky) / 2 - center
    if across.cross(along).length < 1e-8:
        raise ValueError("Degenerate palm plane; cannot infer hand orientation")
    y = along.normalized()
    x = (across - y * across.dot(y)).normalized()
    z = x.cross(y).normalized()
    return Matrix((x, y, z)).transposed()


def main(path):
    job = json.loads(path.read_text(encoding="utf-8"))
    mapping = job["mapping"]
    bpy.ops.wm.open_mainfile(filepath=job["source_skeleton_path"], load_ui=False)
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"
            and all(n in o.pose.bones for n in mapping["source"]["hand_bones"].values())]
    if len(rigs) != 1:
        raise ValueError("Expected one compatible CP2 rig")
    source = rigs[0]
    names = {n for side in mapping["source"]["fingers"].values() for chain in side.values() for n in chain}
    names.update(mapping["source"]["hand_bones"].values())
    axes = mapping["calibration"]["coordinate_axes"]
    axis = Matrix.Identity(3) if axes == "source_z_up_to_target_z_up" else Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
    source_rest = {n: (axis @ (source.matrix_world @ source.data.bones[n].head_local),
                       axis @ (source.matrix_world @ source.data.bones[n].tail_local)) for n in names}
    poses = {}
    if job.get("hand_motion_path"):
        motion_path = Path(job["hand_motion_path"])
        if hashlib.sha256(motion_path.read_bytes()).hexdigest() != job["hand_motion_sha256"]:
            raise ValueError("CP2 hand motion changed")
        motion = json.loads(motion_path.read_text(encoding="utf-8"))
        poses = {int(f): {n: (Vector(p[0]), Vector(p[1])) for n, p in bones.items()}
                 for f, bones in motion["samples"].items()}
    else:
        for frame in range(job["frame_start"], job["frame_end"] + 1):
            bpy.context.scene.frame_set(frame)
            evaluated = source.evaluated_get(bpy.context.evaluated_depsgraph_get())
            poses[frame] = {n: (axis @ (evaluated.matrix_world @ evaluated.pose.bones[n].head),
                                axis @ (evaluated.matrix_world @ evaluated.pose.bones[n].tail)) for n in names}
    bpy.ops.wm.open_mainfile(filepath=job["avatar_work_path"], load_ui=False)
    scene = bpy.context.scene
    target = bpy.data.objects[mapping["target"]["armature"]]
    preserved = {a.name: action_digest(a) for a in bpy.data.actions}
    for a in bpy.data.actions:
        a.use_fake_user = True
    target.animation_data_clear()
    target.animation_data_create()
    action = bpy.data.actions.new("CP3_" + job["clip_id"])
    action.use_fake_user = True
    target.animation_data.action = action
    rest = {b.name: (target.matrix_world @ b.head_local, target.matrix_world @ b.tail_local)
            for b in target.data.bones}
    ratios = []
    for side in ("right", "left"):
        for finger, chain in mapping["target"]["fingers"][side].items():
            if finger != "thumb":
                src = mapping["source"]["fingers"][side][finger]
                reference_poses = poses.values() if job.get("hand_motion_path") else [source_rest]
                for reference in reference_poses:
                    ratios.append(sum((rest[n][1] - rest[n][0]).length for n in chain) /
                                  sum((reference[n][1] - reference[n][0]).length for n in src))
    scale = statistics.median(ratios)
    roots = {side: [c[0] for c in mapping["target"]["fingers"][side].values()] for side in ("right", "left")}
    centers = {side: sum((rest[n][0] for n in roots[side]), Vector()) / 5 for side in roots}
    rest_palms = {side: palm_basis(centers[side],
        rest[mapping["target"]["fingers"][side]["index"][0]][1],
        rest[mapping["target"]["fingers"][side]["pinky"][0]][1]) for side in roots}
    target_center = (centers["right"] + centers["left"]) / 2
    first = poses[job["frame_start"]]
    source_center = sum((first[n][0] for n in mapping["source"]["hand_bones"].values()), Vector()) / 2
    scene.frame_start, scene.frame_end = job["frame_start"], job["frame_end"]
    scene.render.fps, scene.render.fps_base = job["fps"], job["fps_base"]
    samples = {}
    previous = {}
    previous_palms = {}
    palm_spans = {side: statistics.median(
        (p[mapping["source"]["fingers"][side]["index"][0]][1]
         - p[mapping["source"]["fingers"][side]["pinky"][0]][1]).length for p in poses.values())
        for side in ("right", "left")}
    orientation_fallbacks = []
    for frame, pose in poses.items():
        scene.frame_set(frame)
        for side in ("right", "left"):
            wrist = pose[mapping["source"]["hand_bones"][side]][0]
            index_point = pose[mapping["source"]["fingers"][side]["index"][0]][1]
            pinky_point = pose[mapping["source"]["fingers"][side]["pinky"][0]][1]
            across = index_point - pinky_point
            along = (index_point + pinky_point) / 2 - wrist
            condition = across.cross(along).length / max(across.length * along.length, 1e-12)
            unreliable = condition < 0.25 or across.length < palm_spans[side] * 0.3
            if unreliable and side in previous_palms:
                palm = previous_palms[side]
                orientation_fallbacks.append({"frame": frame, "hand": side,
                    "reason": "Palm landmarks collapsed; last reliable orientation retained",
                    "plane_condition": condition})
            else:
                palm = palm_basis(wrist, index_point, pinky_point)
                previous_palms[side] = palm.copy()
            hand_rotation = palm @ rest_palms[side].transposed()
            for finger, chain in mapping["target"]["fingers"][side].items():
                src_chain = mapping["source"]["fingers"][side][finger]
                for index, (name, src_name) in enumerate(zip(chain, src_chain)):
                    bone = target.pose.bones[name]
                    rest_direction = rest[name][1] - rest[name][0]
                    direction = pose[src_name][1] - pose[src_name][0]
                    if direction.length < 1e-8:
                        raise ValueError(f"Degenerate CP2 bone {src_name} at frame {frame}")
                    # Palm orientation carries roll; the per-bone swing carries articulation.
                    rotation = (hand_rotation @ rest_direction).rotation_difference(direction).to_matrix() @ hand_rotation
                    orientation = rotation @ (target.matrix_world @ bone.bone.matrix_local).to_3x3().normalized()
                    matrix = orientation.to_4x4()
                    if index == 0:
                        matrix.translation = (target_center + scale * (wrist - source_center)
                                              + hand_rotation @ (rest[name][0] - centers[side]))
                    else:
                        matrix.translation = target.matrix_world @ target.pose.bones[chain[index - 1]].tail
                    bone.rotation_mode = "QUATERNION"
                    bone.matrix = target.matrix_world.inverted() @ matrix
                    bpy.context.view_layer.update()
                    if name in previous and previous[name].dot(bone.rotation_quaternion) < 0:
                        bone.rotation_quaternion.negate()
                    previous[name] = bone.rotation_quaternion.copy()
                    for channel in ("location", "rotation_quaternion", "scale"):
                        bone.keyframe_insert(data_path=channel, frame=frame, group=name)
        bpy.context.view_layer.update()
        values = {b.name: [list(row) for row in b.matrix] for b in target.pose.bones}
        if not all(math.isfinite(v) for mat in values.values() for row in mat for v in row):
            raise ValueError(f"Non-finite target transform at {frame}")
        samples[str(frame)] = values
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:
                        key.interpolation = "LINEAR"
    if preserved != {name: action_digest(bpy.data.actions[name]) for name in preserved}:
        raise ValueError("Manual Actions were modified")
    scene.frame_set(scene.frame_start)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(path.parent / "retargeted.blend"), compress=True)
    result = {"status": "completed", "action": action.name, "frame_start": scene.frame_start,
              "frame_end": scene.frame_end, "fps": scene.render.fps, "fps_base": scene.render.fps_base,
              "hand_scale": scale, "preserved_actions": preserved, "samples": samples,
              "bone_count": len(target.pose.bones), "blender_version": bpy.app.version_string,
              "method": "palm_frame_and_per_bone_direction_swing", "visual_status": "pending",
              "motion_input": mapping["source"].get("motion_input", "evaluated_cp2_rig"),
              "scale_method": mapping["calibration"]["hand_scale"],
              "orientation_fallbacks": orientation_fallbacks}
    (path.parent / "retarget-result.json").write_text(json.dumps(result, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
