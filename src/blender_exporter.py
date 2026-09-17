import os
import sys
import site
import subprocess
from pathlib import Path
from typing import Optional

class BlenderExporter:
    """
    Manages headless execution of Blender (--background)
    to convert FreeMoCap 3D coordinate trajectories into animation assets (.blend, .fbx, .gltf, .mp4).
    """
    def __init__(self, blender_executable: Path, custom_export_script: Optional[Path] = None):
        self.blender_executable = Path(blender_executable).resolve()
        self.site_packages_dir = self._resolve_site_packages()
        self.export_script = self._resolve_export_script(custom_export_script)

    def _resolve_site_packages(self) -> Path:
        """
        Resolves the site-packages directory of the active Python environment where freemocap is installed.
        """
        try:
            import freemocap
            return Path(freemocap.__file__).parent.parent.resolve()
        except (ImportError, ModuleNotFoundError):
            site_dirs = site.getsitepackages() if hasattr(site, 'getsitepackages') else []
            if site_dirs:
                return Path(site_dirs[0]).resolve()
            return Path(sys.prefix) / "Lib" / "site-packages"

    def _resolve_export_script(self, custom_script: Optional[Path]) -> Path:
        """
        Locates the run_blender_export.py helper script within the installed freemocap package.
        """
        if custom_script and Path(custom_script).exists():
            return Path(custom_script).resolve()

        try:
            import freemocap
            script_path = Path(freemocap.__file__).parent / "core" / "blender" / "helpers" / "run_blender_export.py"
            if script_path.exists():
                return script_path.resolve()
        except (ImportError, ModuleNotFoundError):
            pass

        # Local fallback for development or local copy
        local_fallback = Path(__file__).parent.parent / "_internal" / "freemocap" / "core" / "blender" / "helpers" / "run_blender_export.py"
        if local_fallback.exists():
            return local_fallback.resolve()

        return Path("run_blender_export.py")

    def export_animation(self, session_dir: Path, output_blend_path: Path) -> Path:
        """
        Executes Blender in headless background mode by invoking run_blender_export.py.
        """
        if not self.blender_executable.exists():
            raise FileNotFoundError(f"Blender executable not found at: {self.blender_executable}")

        if not self.export_script.exists():
            raise FileNotFoundError(
                f"Blender export helper script not found: {self.export_script}. "
                "Ensure that 'freemocap' is installed in your Python environment."
            )

        session_dir = Path(session_dir).resolve()
        output_blend_path = Path(output_blend_path).resolve()
        output_blend_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.blender_executable),
            "--background",
            "--python", str(self.export_script),
            "--",
            str(self.site_packages_dir),
            str(session_dir),
            str(output_blend_path)
        ]

        print(f"[BlenderExporter] Invoking Blender in headless background mode...")
        print(f"[BlenderExporter] Command: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[BlenderExporter] STDOUT:\n{result.stdout}")
            print(f"[BlenderExporter] STDERR:\n{result.stderr}")
            raise RuntimeError(f"Blender process exited with error code {result.returncode}.")

        print(f"[BlenderExporter] Animation exported successfully to: {output_blend_path}")
        return output_blend_path
