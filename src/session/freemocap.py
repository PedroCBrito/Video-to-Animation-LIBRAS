"""Create and validate the minimal FreeMoCap recording layout.

This module stops at a discoverable recording. It does not execute FreeMoCap;
the external integration is handled separately. The prepared artifact is hard-linked
when possible, avoiding an unnecessary second copy on the same filesystem.
"""

import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable

from src.common import sha256_file, utc_now, write_json_atomic
from src.ingestion.contracts import SUPPORTED_EXTENSIONS


class SessionError(ValueError):
    """Raised when a FreeMoCap session cannot be created or verified."""


def validate_recording_layout(recording: Path, expected_sha256: str) -> dict[str, Any]:
    """Verify that the backend will see exactly one prepared video."""
    recording = Path(recording).resolve()
    videos = recording / "synchronized_videos"
    if not videos.is_dir():
        raise SessionError(f"Missing FreeMoCap directory: {videos}")
    files = sorted((path for path in videos.iterdir() if path.is_file()), key=lambda path: path.name)
    if len(files) != 1:
        raise SessionError(f"Expected exactly one synchronized video, found {len(files)}.")
    video = files[0]
    if video.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise SessionError(f"Unsupported synchronized video: {video.name}")
    actual = sha256_file(video)
    if actual != expected_sha256:
        raise SessionError("Synchronized video hash does not match the prepared artifact.")
    return {
        "recording": str(recording),
        "synchronized_videos": str(videos),
        "video": str(video),
        "video_name": video.name,
        "video_count": 1,
        "video_sha256": actual,
        "discoverable": True,
    }


def _materialize_video(source: Path, destination: Path) -> str:
    """Publish one hard link or copy atomically, without overwriting files."""
    if destination.exists():
        raise SessionError(f"Session destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        try:
            os.link(source, temporary)
            method = "hardlink"
        except OSError:
            shutil.copy2(source, temporary)
            method = "copy"
        if not temporary.is_file() or sha256_file(temporary) != sha256_file(source):
            raise SessionError("Materialized session video failed hash verification.")
        os.replace(temporary, destination)
        return method
    finally:
        temporary.unlink(missing_ok=True)


def create_session(preparation: dict[str, Any], output_root: Path) -> dict[str, Any]:
    """Materialize one prepared manifest into a FreeMoCap recording layout."""
    if preparation.get("status") != "prepared":
        raise SessionError("Only a successful preparation can become a session.")
    prepared = Path(preparation["output_path"]).resolve(strict=True)
    expected = preparation.get("output_sha256")
    if not expected or sha256_file(prepared) != expected:
        raise SessionError("Prepared artifact is missing or its hash does not match its manifest.")
    run_root = prepared.parent.parent
    if run_root.parent.parent != Path(output_root).resolve() / "work":
        raise SessionError("Prepared artifact is outside the configured work directory.")
    source_manifest_path = run_root / "source.json"
    if source_manifest_path.exists():
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        if source_manifest.get("source_sha256") != preparation.get("source_sha256", source_manifest.get("source_sha256")):
            raise SessionError("Source manifest does not match the prepared artifact.")
    else:
        write_json_atomic(source_manifest_path, {
            "schema_version": "1.0", "stage": "source", "created_at": utc_now(),
            "clip_id": preparation["clip_id"], "source_path": preparation.get("source_path"),
            "source_relative_path": preparation.get("source_relative_path"),
            "source_sha256": preparation.get("source_sha256"),
        })
    recording = run_root / "freemocap"
    videos = recording / "synchronized_videos"
    destination = videos / ("camera_01" + prepared.suffix.lower())
    session_manifest_path = recording / "session.json"
    if session_manifest_path.exists():
        previous = json.loads(session_manifest_path.read_text(encoding="utf-8"))
        if previous.get("prepared_sha256") != expected:
            raise SessionError("Existing session does not match the prepared artifact.")
        layout = validate_recording_layout(recording, expected)
        return {**previous, "status": "session_ready", "reused": True, "layout": layout}
    if recording.exists() and any(recording.rglob("*")):
        raise SessionError("Session workspace exists without a complete session manifest.")

    method = _materialize_video(prepared, destination)
    layout = validate_recording_layout(recording, expected)
    manifest = {
        "schema_version": "1.0", "stage": "session", "status": "session_ready",
        "created_at": utc_now(), "clip_id": preparation["clip_id"],
        "run_id": preparation["run_id"], "prepared_path": str(prepared),
        "prepared_sha256": expected, "recording_path": str(recording),
        "layout_contract": "freemocap_recording_v1",
        "materialization": method, "layout": layout, "reused": False,
    }
    write_json_atomic(session_manifest_path, manifest)
    return manifest


def create_sessions(
    report: dict[str, Any],
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Create sessions for prepared entries while preserving individual failures."""
    report["stage"] = "session"
    counts: dict[str, int] = {}
    total = len(report["entries"])
    for index, entry in enumerate(report["entries"], start=1):
        preparation = entry.get("preparation", {})
        if preparation.get("status") != "prepared":
            result = {"status": "not_run", "reason": f"preparation_status:{preparation.get('status', 'missing')}"}
        else:
            try:
                result = create_session(preparation, Path(report["output"]))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                result = {"status": "failed", "reason": str(error)}
        entry["session"] = result
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if progress_callback is not None:
            progress_callback(index, total, entry)
    report["session_summary"] = counts
    report["finished_at"] = utc_now()
    return report


def session_exit_code(report: dict[str, Any]) -> int:
    """Return 0 only when every input has a verified session."""
    if not report.get("session_summary", {}).get("session_ready"):
        return 2
    if any(entry["status"] != "valid" for entry in report["entries"]):
        return 2
    summary = report["session_summary"]
    return 0 if not summary.get("failed") and not summary.get("not_run") else 2
