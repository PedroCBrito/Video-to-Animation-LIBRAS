"""Isolated FreeMoCap process adapter."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import importlib.util
from pathlib import Path
import sys
from typing import Any, Mapping

from src.integrations.environment import check_python_package
from src.integrations.process import ProcessResult, run_process


class FreeMoCapAdapterError(ValueError):
    """Raised when the backend adapter cannot construct a safe execution."""


def _replace_tokens(value: str, tokens: Mapping[str, str]) -> str:
    result = value
    for name, replacement in tokens.items():
        result = result.replace("{" + name + "}", replacement)
    return result


@dataclass(frozen=True)
class FreeMoCapAdapter:
    """Invoke a configured FreeMoCap entrypoint in an isolated Python process."""

    python_executable: Path | str = sys.executable
    entrypoint: str | None = None
    session_argument: str = "recording_session_path"
    command_template: tuple[str, ...] | None = None
    project_root: Path | None = None
    package_name: str = "freemocap"

    def __post_init__(self) -> None:
        if not self.session_argument.isidentifier():
            raise FreeMoCapAdapterError("Session argument must be a valid Python identifier.")
        if self.entrypoint and ":" not in self.entrypoint:
            raise FreeMoCapAdapterError("Entrypoint must use the module:function format.")
        if not self.command_template and not self.entrypoint:
            raise FreeMoCapAdapterError("An entrypoint or command template is required.")

    @property
    def root(self) -> Path:
        return Path(self.project_root or Path(__file__).parents[2]).resolve()

    def identity(self) -> dict[str, str | None]:
        """Return values that participate in extraction compatibility."""
        return {
            "package": self.package_name,
            "python": str(Path(self.python_executable).resolve()),
            "entrypoint": self.entrypoint,
            "session_argument": self.session_argument,
        }

    def preflight(self) -> dict[str, Any]:
        """Inspect the package and adapter contract without importing FreeMoCap."""
        package = check_python_package(
            self.package_name,
            module_finder=importlib.util.find_spec,
            version_reader=importlib.metadata.version,
        )
        return {
            "adapter": self.identity(),
            "package": package,
            "entrypoint_configured": bool(self.entrypoint or self.command_template),
            "python_exists": Path(self.python_executable).is_file(),
            "ready": bool(package["available"] and (self.entrypoint or self.command_template)
                           and Path(self.python_executable).is_file()),
        }

    def build_command(self, session_dir: Path, config_path: Path | None = None) -> list[str]:
        """Build an argv list for the isolated worker."""
        session = str(Path(session_dir).resolve())
        config = str(Path(config_path).resolve()) if config_path else ""
        tokens = {
            "session_dir": session,
            "config_path": config,
            "entrypoint": self.entrypoint or "",
            "session_argument": self.session_argument,
        }
        if self.command_template:
            return [_replace_tokens(str(part), tokens) for part in self.command_template]
        if not self.entrypoint:
            raise FreeMoCapAdapterError("An entrypoint is required for the default worker.")
        command = [
            str(Path(self.python_executable).resolve()),
            "-m", "src.integrations.freemocap_worker",
            "--session", session,
            "--entrypoint", self.entrypoint,
            "--session-argument", self.session_argument,
        ]
        if config_path:
            command.extend(("--config", config))
        return command

    def process_session(
        self,
        session_dir: Path,
        *,
        config_path: Path | None = None,
        timeout: float = 3600,
        cancel_event: Any | None = None,
    ) -> ProcessResult:
        """Run one recording session and return captured process evidence."""
        session_dir = Path(session_dir).resolve()
        if not session_dir.is_dir():
            raise FreeMoCapAdapterError(f"Session directory does not exist: {session_dir}")
        command = self.build_command(session_dir, config_path)
        return run_process(
            command, cwd=self.root, timeout=timeout, cancel_event=cancel_event,
        )
