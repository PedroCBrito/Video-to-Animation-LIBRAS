"""Environment contract and preflight for the extraction backend."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Sequence

from src.common import sha256_file, utc_now, write_json_atomic
from src.session.freemocap import SessionError, validate_recording_layout


class EnvironmentContractError(ValueError):
    """Raised when a required environment contract cannot be collected."""


@dataclass(frozen=True)
class ToolCheck:
    """Version and availability information for one executable."""

    name: str
    requested: str | None
    path: str | None
    available: bool
    version: str | None
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "requested": self.requested,
            "path": self.path,
            "available": self.available,
            "version": self.version,
            "error": self.error,
        }


@dataclass(frozen=True)
class EnvironmentContract:
    """Serializable snapshot used to identify an extraction environment."""

    schema_version: str
    created_at: str
    python: dict[str, Any]
    tools: dict[str, ToolCheck]
    freemocap: dict[str, Any]
    backend: dict[str, Any]
    reference_session: dict[str, Any]
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "python": self.python,
            "tools": {name: check.as_dict() for name, check in self.tools.items()},
            "freemocap": self.freemocap,
            "backend": self.backend,
            "reference_session": self.reference_session,
            "status": self.status,
        }


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ModuleFinder = Callable[[str], object | None]
VersionReader = Callable[[str], str]


def _resolve_executable(requested: str | None, fallback: str) -> tuple[str | None, str | None]:
    value = requested or fallback
    found = shutil.which(value)
    if found:
        return str(Path(found).resolve()), None
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return str(candidate.resolve()), None
    return None, f"Executable não encontrado: {value}"


def check_tool(
    name: str,
    requested: str | None,
    fallback: str,
    *,
    runner: CommandRunner = subprocess.run,
) -> ToolCheck:
    """Resolve an executable and collect its version without changing files."""
    path, error = _resolve_executable(requested, fallback)
    if path is None:
        return ToolCheck(name, requested, None, False, None, error)
    try:
        result = runner(
            [path, "--version"], stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolCheck(name, requested, path, False, None, f"Não foi possível executar: {exc}")
    output = (result.stdout or result.stderr or "").strip()
    version = output.splitlines()[0] if output else None
    if result.returncode != 0:
        return ToolCheck(name, requested, path, False, version, f"Saiu com código {result.returncode}.")
    return ToolCheck(name, requested, path, True, version, None)


def check_python_package(
    package: str = "freemocap",
    *,
    module_finder: ModuleFinder = importlib.util.find_spec,
    version_reader: VersionReader = importlib.metadata.version,
) -> dict[str, Any]:
    """Inspect a Python package without importing its heavy runtime modules."""
    try:
        spec = module_finder(package)
    except (ImportError, ModuleNotFoundError) as exc:
        spec = None
        error = str(exc)
    else:
        error = None
    if spec is None:
        return {"name": package, "available": False, "version": None, "location": None,
                "error": error or "Pacote não encontrado no ambiente Python."}
    location = getattr(spec, "origin", None)
    try:
        version = version_reader(package)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {"name": package, "available": True, "version": version,
            "location": str(location) if location else None, "error": None}


def _reference_session_contract(recording: Path | None) -> dict[str, Any]:
    if recording is None:
        return {"provided": False, "valid": False, "error": "Sessão de referência não informada."}
    recording = Path(recording).resolve()
    manifest_path = recording / "session.json"
    if not manifest_path.is_file():
        return {"provided": True, "valid": False, "path": str(recording),
                "error": f"Manifesto de sessão ausente: {manifest_path}"}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_hash = manifest["prepared_sha256"]
        layout = validate_recording_layout(recording, expected_hash)
    except (OSError, KeyError, json.JSONDecodeError, SessionError, ValueError) as exc:
        return {"provided": True, "valid": False, "path": str(recording), "error": str(exc)}
    return {
        "provided": True,
        "valid": True,
        "path": str(recording),
        "manifest_sha256": sha256_file(manifest_path),
        "prepared_sha256": expected_hash,
        "video": layout["video_name"],
        "video_sha256": layout["video_sha256"],
        "layout_contract": manifest.get("layout_contract"),
    }


def collect_environment_contract(
    *,
    reference_session: Path | None = None,
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
    blender: str | None = None,
    backend_entrypoint: str | None = None,
    runner: CommandRunner = subprocess.run,
    module_finder: ModuleFinder = importlib.util.find_spec,
    version_reader: VersionReader = importlib.metadata.version,
) -> EnvironmentContract:
    """Collect the reproducible environment contract for CP2."""
    tools = {
        "ffmpeg": check_tool("ffmpeg", ffmpeg, "ffmpeg", runner=runner),
        "ffprobe": check_tool("ffprobe", ffprobe, "ffprobe", runner=runner),
        "blender": check_tool("blender", blender, "blender", runner=runner),
    }
    freemocap = check_python_package(
        "freemocap", module_finder=module_finder, version_reader=version_reader,
    )
    reference = _reference_session_contract(reference_session)
    backend = {
        "entrypoint": backend_entrypoint,
        "entrypoint_confirmed": bool(backend_entrypoint),
        "execution_mode": "isolated-python-worker",
    }
    complete = (
        all(check.available for check in tools.values())
        and bool(freemocap["available"])
        and reference["valid"]
        and bool(backend_entrypoint)
    )
    return EnvironmentContract(
        schema_version="1.0",
        created_at=utc_now(),
        python={"executable": str(Path(sys.executable).resolve()), "version": sys.version},
        tools=tools,
        freemocap=freemocap,
        backend=backend,
        reference_session=reference,
        status="ready" if complete else "incomplete",
    )


def write_environment_contract(destination: Path, contract: EnvironmentContract) -> Path:
    """Publish a complete environment contract atomically."""
    destination = Path(destination).resolve()
    write_json_atomic(destination, contract.as_dict())
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    """Run the environment preflight as a small standalone command."""
    import argparse

    parser = argparse.ArgumentParser(description="Collect the FreeMoCap extraction environment contract.")
    parser.add_argument("--output", type=Path, default=Path("output/environment.json"))
    parser.add_argument("--reference-session", type=Path)
    parser.add_argument("--backend-entrypoint")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--blender")
    args = parser.parse_args(argv)
    contract = collect_environment_contract(
        reference_session=args.reference_session,
        ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, blender=args.blender,
        backend_entrypoint=args.backend_entrypoint,
    )
    destination = write_environment_contract(args.output, contract)
    print(f"Environment contract: {destination}")
    print(f"Status: {contract.status}")
    return 0 if contract.status == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
