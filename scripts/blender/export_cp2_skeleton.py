"""Export the FreeMoCap 1.8.2 AJC source scene with Blender's Python.

Arguments after --: site-packages directory, recording directory, output .blend.
"""

from fractions import Fraction
import json
from pathlib import Path
import sys


def main() -> None:
    if "--" not in sys.argv or len(sys.argv[sys.argv.index("--") + 1:]) != 3:
        raise ValueError("Expected -- SITE_PACKAGES RECORDING OUTPUT")
    site_packages, recording, output = [Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1:]]
    if not (site_packages / "ajc27_freemocap_blender_addon").is_dir():
        raise FileNotFoundError("FreeMoCap AJC Blender addon is missing")
    if not (recording / "output_data" / "mediapipe_right_hand_3d_xyz.npy").is_file():
        raise FileNotFoundError("FreeMoCap right hand data is missing")
    if not (recording / "output_data" / "mediapipe_left_hand_3d_xyz.npy").is_file():
        raise FileNotFoundError("FreeMoCap left hand data is missing")
    sys.path.insert(0, str(site_packages))
    from ajc27_freemocap_blender_addon.main import ajc27_run_as_main_function
    # Keep the addon's package path, but let Blender load its own compiled numpy.
    sys.path.remove(str(site_packages))

    output.parent.mkdir(parents=True, exist_ok=True)
    ajc27_run_as_main_function(recording_path=str(recording), blend_file_path=str(output))
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("AJC addon finished without saving a Blender scene")
    session = json.loads((recording / "session.json").read_text(encoding="utf-8"))
    prepared = Path(session["prepared_path"])
    preparation = json.loads((prepared.parent.parent / "preparation.json").read_text(encoding="utf-8"))
    fps = Fraction(preparation["validation"]["fps_average"])
    frames = preparation["validation"]["decoded_frame_count"]
    if fps <= 0 or not isinstance(frames, int) or frames <= 0:
        raise ValueError("Prepared media has no valid frame rate or frame count")
    import bpy
    scene = bpy.context.scene
    scene.render.fps = round(float(fps))
    scene.render.fps_base = scene.render.fps / float(fps)
    scene.frame_start = 0
    scene.frame_end = frames - 1
    scene.frame_set(0)
    bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=True)


if __name__ == "__main__":
    main()
