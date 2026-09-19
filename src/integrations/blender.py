"""Controlled Blender invocation for source skeleton export."""

from __future__ import annotations

import site
import sys
import importlib.util
from pathlib import Path
from typing import Sequence

from src.integrations.process import ProcessResult, run_process


class BlenderExporter:
    """Build and execute a headless Blender export command."""

    def __init__(
        self,
        blender_executable: Path,
        custom_export_script: Path | None = None,
        *,
        command_template: Sequence[str] | None = None,
        process_runner=run_process,
    ):
        self.blender_executable = Path(blender_executable).resolve()
        self.site_packages_dir = self._resolve_site_packages()
        self.export_script = self._resolve_export_script(custom_export_script)
        self.command_template = tuple(command_template) if command_template else None
        self._process_runner = process_runner

    def _resolve_site_packages(self) -> Path:
        try:
            spec = importlib.util.find_spec("freemocap")
            if spec is not None and spec.origin:
                return Path(spec.origin).parent.parent.resolve()
        except (ImportError, ModuleNotFoundError, ValueError):
            pass
        try:
            site_dirs = site.getsitepackages() if hasattr(site, "getsitepackages") else []
            return Path(site_dirs[0]).resolve() if site_dirs else Path(sys.prefix) / "Lib" / "site-packages"
        except (IndexError, OSError):
            return Path(sys.prefix) / "Lib" / "site-packages"

    def _resolve_export_script(self, custom_script: Path | None) -> Path:
        if custom_script and Path(custom_script).exists():
            return Path(custom_script).resolve()
        try:
            spec = importlib.util.find_spec("freemocap")
            if spec is not None and spec.origin:
                script_path = Path(spec.origin).parent / "core" / "blender" / "helpers" / "run_blender_export.py"
                if script_path.exists():
                    return script_path.resolve()
        except (ImportError, ModuleNotFoundError, ValueError):
            pass
        local_fallback = Path(__file__).parents[2] / "_internal" / "freemocap" / "core" / "blender" / "helpers" / "run_blender_export.py"
        return local_fallback.resolve() if local_fallback.exists() else Path("run_blender_export.py")

    def build_command(self, session_dir: Path, output_blend_path: Path) -> tuple[str, ...]:
        """Return the argv used for one export, without starting a process."""
        values = {
            "blender": str(self.blender_executable), "script": str(self.export_script),
            "site_packages": str(self.site_packages_dir),
            "session_dir": str(Path(session_dir).resolve()),
            "output_blend": str(Path(output_blend_path).resolve()),
        }
        if self.command_template:
            try:
                return tuple(str(argument).format_map(values) for argument in self.command_template)
            except KeyError as error:
                raise ValueError(f"Unknown Blender command template value: {error.args[0]}") from error
        return (
            str(self.blender_executable), "--background", "--python", str(self.export_script), "--",
            values["site_packages"], values["session_dir"], values["output_blend"],
        )

    def run_export(self, session_dir: Path, output_blend_path: Path, *, timeout: float = 3600, cancel_event=None) -> ProcessResult:
        """Run Blender with a controlled argv and return complete process evidence."""
        if not self.blender_executable.is_file():
            return ProcessResult((str(self.blender_executable),), None, "", f"Blender executable not found at: {self.blender_executable}", 0)
        if not self.export_script.is_file() and self.command_template is None:
            return ProcessResult((str(self.blender_executable),), None, "", f"Blender export helper script not found: {self.export_script}", 0)
        output_blend_path = Path(output_blend_path).resolve()
        output_blend_path.parent.mkdir(parents=True, exist_ok=True)
        return self._process_runner(
            self.build_command(session_dir, output_blend_path), cwd=Path(session_dir),
            timeout=timeout, cancel_event=cancel_event,
        )

    def export_animation(self, session_dir: Path, output_blend_path: Path) -> Path:
        """Compatibility wrapper that raises when the export did not succeed."""
        result = self.run_export(session_dir, output_blend_path)
        if not result.succeeded:
            detail = result.stderr.strip()[-4000:]
            raise RuntimeError(f"Blender export failed with code {result.returncode}: {detail}")
        return Path(output_blend_path).resolve()
