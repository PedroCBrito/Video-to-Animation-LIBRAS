"""Render two inspection views of a hand-only avatar without saving the .blend."""

from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main():
    if "--" not in sys.argv or len(sys.argv[sys.argv.index("--") + 1:]) != 1:
        raise ValueError("Expected: -- OUTPUT_DIRECTORY")
    folder = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.frame_set(1)
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name not in {"Mao direita", "mao esquerda"}:
            obj.hide_render = True
    camera_data = bpy.data.cameras.new("Inspection camera")
    camera = bpy.data.objects.new("Inspection camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 5.8
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    target = Vector((0.07, -1.5, -2.7))
    for name, position in (("front", (0.07, -10, -2.7)), ("back", (0.07, 7, -2.7))):
        camera.location = position
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(folder / f"avatar-hands-{name}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
