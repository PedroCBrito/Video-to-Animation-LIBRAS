"""Blender export adapter reserved for a future integration."""

import site
import subprocess
import sys
from pathlib import Path


class BlenderExporter:
    """Invoke Blender headlessly using the installed FreeMoCap helper."""

    def __init__(self, blender_executable: Path, custom_export_script: Path | None = None):
        self.blender_executable = Path(blender_executable).resolve()
        self.site_packages_dir = self._resolve_site_packages()
        self.export_script = self._resolve_export_script(custom_export_script)

    def _resolve_site_packages(self) -> Path:
        try:
            import freemocap
            return Path(freemocap.__file__).parent.parent.resolve()
        except (ImportError, ModuleNotFoundError):
            site_dirs = site.getsitepackages() if hasattr(site, "getsitepackages") else []
            return Path(site_dirs[0]).resolve() if site_dirs else Path(sys.prefix) / "Lib" / "site-packages"

    def _resolve_export_script(self, custom_script: Path | None) -> Path:
        if custom_script and Path(custom_script).exists():
            return Path(custom_script).resolve()
        try:
            import freemocap
            script_path = Path(freemocap.__file__).parent / "core" / "blender" / "helpers" / "run_blender_export.py"
            if script_path.exists():
                return script_path.resolve()
        except (ImportError, ModuleNotFoundError):
            pass
        local_fallback = Path(__file__).parents[2] / "_internal" / "freemocap" / "core" / "blender" / "helpers" / "run_blender_export.py"
        return local_fallback.resolve() if local_fallback.exists() else Path("run_blender_export.py")

    def export_animation(self, session_dir: Path, output_blend_path: Path) -> Path:
        if not self.blender_executable.exists():
            raise FileNotFoundError(f"Blender executable not found at: {self.blender_executable}")
        if not self.export_script.exists():
            raise FileNotFoundError(f"Blender export helper script not found: {self.export_script}")
        output_blend_path = Path(output_blend_path).resolve()
        output_blend_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.blender_executable), "--background", "--python", str(self.export_script), "--",
            str(self.site_packages_dir), str(Path(session_dir).resolve()), str(output_blend_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Blender process exited with error code {result.returncode}: {result.stderr[-4000:]}")
        return output_blend_path
