"""Create and verify the source skeleton Blender artifact for a session."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any

from src.common import sha256_file, utc_now, write_json_atomic
from src.extraction.pipeline import ExtractionError, _load_json
from src.integrations.blender import BlenderExporter
from src.integrations.process import ProcessResult
from src.session.freemocap import SessionError, validate_recording_layout


class SourceSkeletonError(ValueError):
    """Raised when a source skeleton cannot be created or verified."""


@dataclass(frozen=True)
class SourceSkeletonResult:
    """Published source skeleton manifest and its location."""

    manifest: dict[str, Any]
    manifest_path: Path

    @property
    def succeeded(self) -> bool:
        return self.manifest.get("status") == "completed"


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        return _load_json(path)
    except ExtractionError as error:
        raise SourceSkeletonError(str(error)) from error


def _validate_inputs(recording: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    session = _load_manifest(recording / "session.json")
    if session.get("status") != "session_ready":
        raise SourceSkeletonError("Only a session_ready recording can create a source skeleton.")
    extraction = _load_manifest(recording / "freemocap.json")
    if extraction.get("status") != "completed":
        raise SourceSkeletonError("A completed extraction is required before source skeleton export.")
    expected_hash = session.get("prepared_sha256")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise SourceSkeletonError("Session manifest has no prepared video hash.")
    try:
        layout = validate_recording_layout(recording, expected_hash)
    except (OSError, SessionError, ValueError) as error:
        raise SourceSkeletonError(f"Invalid FreeMoCap session: {error}") from error
    return session, {"manifest": extraction, "layout": layout}


def _process_evidence(result: ProcessResult, recording: Path) -> dict[str, Any]:
    logs = recording / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "blender_stdout.log").write_text(result.stdout, encoding="utf-8")
    (logs / "blender_stderr.log").write_text(result.stderr, encoding="utf-8")
    return {
        "command": list(result.command), "returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "timed_out": result.timed_out, "cancelled": result.cancelled,
        "stdout_path": "logs/blender_stdout.log", "stderr_path": "logs/blender_stderr.log",
    }


def _temporary_output(destination: Path) -> Path:
    handle, name = tempfile.mkstemp(prefix=f".{destination.stem}-", suffix=".tmp.blend", dir=destination.parent)
    os.close(handle)
    path = Path(name)
    path.unlink(missing_ok=True)
    return path


def export_source_skeleton(
    recording: Path,
    exporter: BlenderExporter,
    *,
    timeout: float = 3600,
    cancel_event=None,
) -> SourceSkeletonResult:
    """Export ``source_skeleton.blend`` and publish a verifiable manifest."""
    recording = Path(recording).resolve()
    session, extraction_data = _validate_inputs(recording)
    extraction = extraction_data["manifest"]
    destination = recording / "source_skeleton.blend"
    manifest_path = recording / "source_skeleton.json"
    temporary = _temporary_output(destination)
    result = exporter.run_export(recording, temporary, timeout=timeout, cancel_event=cancel_event)
    process = _process_evidence(result, recording)
    status = "failed"
    error = None
    if result.cancelled:
        status, error = "cancelled", "Exportação do esqueleto cancelada pelo usuário."
    elif result.timed_out:
        error = "Exportação do esqueleto excedeu o tempo limite."
    elif not result.succeeded:
        error = "Blender não produziu o esqueleto de origem."
    elif not temporary.is_file() or temporary.stat().st_size == 0:
        error = "Blender terminou sem produzir um arquivo .blend válido."
    else:
        os.replace(temporary, destination)
        status = "completed"
    temporary.unlink(missing_ok=True)
    if status == "failed" and result.stderr.strip():
        error = f"{error} {result.stderr.strip()[-2000:]}"
    manifest = {
        "schema_version": "1.0", "stage": "source_skeleton", "status": status,
        "created_at": utc_now(), "run_id": extraction.get("run_id"),
        "clip_id": extraction.get("clip_id"), "recording_path": str(recording),
        "session_manifest_sha256": sha256_file(recording / "session.json"),
        "extraction_manifest_sha256": sha256_file(recording / "freemocap.json"),
        "output_path": "source_skeleton.blend" if status == "completed" else None,
        "output_sha256": sha256_file(destination) if status == "completed" else None,
        "output_size_bytes": destination.stat().st_size if status == "completed" else None,
        "process": process, "error": error,
    }
    write_json_atomic(manifest_path, manifest)
    return SourceSkeletonResult(manifest, manifest_path)
