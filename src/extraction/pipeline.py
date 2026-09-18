"""Run one FreeMoCap session and publish traceable extraction artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from src.common import sha256_file, utc_now, write_json_atomic
from src.integrations.freemocap import FreeMoCapAdapter
from src.integrations.process import ProcessResult
from src.session.freemocap import SessionError, validate_recording_layout
from src.extraction.profile import ExtractionProfile


class ExtractionError(ValueError):
    """Raised when a session cannot be safely prepared for extraction."""


@dataclass(frozen=True)
class ExtractionResult:
    """Published extraction manifest and its location."""

    manifest: dict[str, Any]
    manifest_path: Path

    @property
    def succeeded(self) -> bool:
        return self.manifest.get("status") == "completed"

    @property
    def reused(self) -> bool:
        return bool(self.manifest.get("reused"))


def _write_text_atomic(destination: Path, content: str) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExtractionError(f"Cannot read JSON contract {path}: {error}") from error
    if not isinstance(data, dict):
        raise ExtractionError(f"JSON contract must be an object: {path}")
    return data


def _validate_session(session_dir: Path) -> tuple[dict[str, Any], str]:
    manifest_path = session_dir / "session.json"
    manifest = _load_json(manifest_path)
    if manifest.get("status") != "session_ready":
        raise ExtractionError("Only a session_ready recording can be extracted.")
    expected_hash = manifest.get("prepared_sha256")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise ExtractionError("Session manifest has no prepared video hash.")
    try:
        validate_recording_layout(session_dir, expected_hash)
    except (OSError, SessionError, ValueError) as error:
        raise ExtractionError(f"Invalid FreeMoCap session: {error}") from error
    return manifest, sha256_file(manifest_path)


def _compatibility(session_manifest: dict[str, Any], session_hash: str,
                   profile: ExtractionProfile, adapter: FreeMoCapAdapter) -> dict[str, Any]:
    return {
        "session_manifest_sha256": session_hash,
        "prepared_sha256": session_manifest["prepared_sha256"],
        "profile_fingerprint": profile.fingerprint,
        "adapter": adapter.identity(),
    }


def _hash_artifacts(recording: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    output_data = recording / "output_data"
    if not output_data.is_dir():
        return artifacts
    for path in sorted(item for item in output_data.rglob("*") if item.is_file()):
        artifacts.append({
            "path": path.relative_to(recording).as_posix(),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        })
    return artifacts


def _outputs(recording: Path, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    output_data = recording / "output_data"
    raw_data = output_data / "raw_data"
    processed_data = output_data / "processed_data"
    return {
        "output_data": {"path": "output_data", "exists": output_data.is_dir(),
                        "file_count": len(artifacts)},
        "raw_data": {"path": "output_data/raw_data", "exists": raw_data.is_dir()},
        "processed_data": {"path": "output_data/processed_data", "exists": processed_data.is_dir()},
    }


def _outputs_are_valid(recording: Path, manifest: dict[str, Any]) -> bool:
    expected = manifest.get("artifacts", [])
    if manifest.get("status") != "completed" or not expected:
        return False
    for artifact in expected:
        path = recording / artifact["path"]
        if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
            return False
    return bool(manifest.get("outputs", {}).get("output_data", {}).get("exists"))


def _process_evidence(result: ProcessResult, logs: Path) -> dict[str, Any]:
    _write_text_atomic(logs / "stdout.log", result.stdout)
    _write_text_atomic(logs / "stderr.log", result.stderr)
    return {
        "command": list(result.command),
        "returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "timed_out": result.timed_out,
        "cancelled": result.cancelled,
        "stdout_path": "logs/stdout.log",
        "stderr_path": "logs/stderr.log",
    }


def run_extraction(
    session_dir: Path,
    profile: ExtractionProfile,
    adapter: FreeMoCapAdapter,
    *,
    timeout: float = 3600,
    cancel_event: Any | None = None,
) -> ExtractionResult:
    """Execute or safely reuse one compatible extraction session."""
    session_dir = Path(session_dir).resolve()
    session_manifest, session_hash = _validate_session(session_dir)
    manifest_path = session_dir / "freemocap.json"
    compatibility = _compatibility(session_manifest, session_hash, profile, adapter)

    if manifest_path.is_file():
        previous = _load_json(manifest_path)
        if previous.get("status") == "completed":
            if previous.get("compatibility") != compatibility:
                raise ExtractionError("Existing extraction uses a different input, profile or adapter.")
            if _outputs_are_valid(session_dir, previous):
                return ExtractionResult({**previous, "reused": True}, manifest_path)
            raise ExtractionError("Existing completed extraction has missing or changed artifacts.")

    logs = session_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    profile_path = session_dir / "profile.effective.json"
    write_json_atomic(profile_path, profile.as_dict())
    started_at = utc_now()
    result = adapter.process_session(
        session_dir, config_path=profile_path, timeout=timeout, cancel_event=cancel_event,
    )
    process = _process_evidence(result, logs)
    artifacts = _hash_artifacts(session_dir)
    outputs = _outputs(session_dir, artifacts)
    status = "completed" if result.succeeded and outputs["output_data"]["exists"] and artifacts else (
        "cancelled" if result.cancelled else "failed"
    )
    error = None
    if status == "cancelled":
        error = "Extração cancelada pelo usuário."
    elif status == "failed":
        error = "Backend não produziu uma saída válida."
        if result.stderr.strip():
            error = f"{error} {result.stderr.strip()[-2000:]}"
    manifest = {
        "schema_version": "1.0",
        "stage": "extract",
        "status": status,
        "reused": False,
        "created_at": started_at,
        "finished_at": utc_now(),
        "clip_id": session_manifest.get("clip_id"),
        "run_id": session_manifest.get("run_id"),
        "session_path": str(session_dir),
        "session_manifest_sha256": session_hash,
        "compatibility": compatibility,
        "profile_path": "profile.effective.json",
        "profile_fingerprint": profile.fingerprint,
        "adapter": adapter.identity(),
        "process": process,
        "outputs": outputs,
        "artifacts": artifacts,
        "error": error,
    }
    write_json_atomic(manifest_path, manifest)
    return ExtractionResult(manifest, manifest_path)
