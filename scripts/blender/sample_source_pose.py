"""Sample evaluated CP2 hand poses for calibration (read-only)."""

import json
from pathlib import Path
import sys

import bpy


def main():
    if "--" not in sys.argv or len(sys.argv[sys.argv.index("--") + 1:]) != 3:
        raise ValueError("Expected -- SOURCE MAP OUTPUT")
    source_path, map_path, output_path = [Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1:]]
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(source_path), load_ui=False)
    rig = next(obj for obj in bpy.data.objects if obj.type == "ARMATURE" and "hand.R" in obj.pose.bones)
    names = sorted({name for side in mapping["source"]["fingers"].values()
                    for chain in side.values() for name in chain} | set(mapping["source"]["hand_bones"].values()))
    scene = bpy.context.scene
    frames = sorted({scene.frame_start, 1, 30, 60, 90, 120, scene.frame_end - 1})
    samples = {}
    for frame in frames:
        scene.frame_set(frame)
        evaluated = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        samples[str(frame)] = {name: {
            "head": list(evaluated.pose.bones[name].head),
            "tail": list(evaluated.pose.bones[name].tail),
            "matrix": [list(row) for row in evaluated.pose.bones[name].matrix],
        } for name in names}
    output_path.write_text(json.dumps({"fps": scene.render.fps, "frames": frames, "samples": samples},
                                      allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
