"""Render synchronized diagnostic frames with fixed framing across the clip."""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector


def main(path):
    job = json.loads(path.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(path.parent / "retargeted.blend"), load_ui=False)
    scene = bpy.context.scene
    meshes = [bpy.data.objects[n] for n in job["mapping"]["target"]["meshes"].values()]
    bounds = []
    frames = list(range(scene.frame_start, scene.frame_end + 1))
    for f in frames:
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        for obj in meshes:
            evaluated = obj.evaluated_get(deps)
            bounds.extend(evaluated.matrix_world @ Vector(p) for p in evaluated.bound_box)
    low = Vector([min(p[i] for p in bounds) for i in range(3)])
    high = Vector([max(p[i] for p in bounds) for i in range(3)])
    center = (low + high) / 2
    camera = bpy.data.objects.new("CP3_preview", bpy.data.cameras.new("CP3_preview"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.location = center + Vector((0, -30, 0))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(high.x - low.x, high.z - low.z) * 1.15
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "OBJECT"
    meshes[0].color = (0.12, 0.5, 0.85, 1)
    meshes[1].color = (0.9, 0.4, 0.12, 1)
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    folder = path.parent / "preview"
    folder.mkdir(exist_ok=True)
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = str(folder / f"avatar-{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    (folder / "frames.json").write_text(json.dumps({"frames": frames, "fps": scene.render.fps / scene.render.fps_base,
        "right_color": "blue", "left_color": "orange", "camera": "front_negative_y"}), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
