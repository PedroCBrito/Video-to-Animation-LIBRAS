"""Verification of prepared media and FreeMoCap session layout."""

from fractions import Fraction
import json
from pathlib import Path
import time
from typing import Any, Callable

from src.common import sha256_file, utc_now, write_json_atomic
from src.session import validate_recording_layout


class VerificationError(ValueError):
    """Raised for an unrecoverable verification contract violation."""


def _duration_seconds(inspection: dict[str, Any]) -> float | None:
    return inspection.get("stream_duration_seconds") or inspection.get("container_duration_seconds")


def _fps_value(inspection: dict[str, Any]) -> float:
    """Convert the rational FPS strings emitted by media inspection safely."""
    value = inspection.get("fps_average") or inspection.get("fps_nominal") or "30"
    try:
        fps = float(Fraction(str(value)))
        return fps if fps > 0 else 30.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 30.0


def verify_entry(
    entry: dict[str, Any], *, inspector: Callable[[Path], dict[str, Any]],
    output_root: Path,
) -> dict[str, Any]:
    """Verify one prepared artifact and the video visible to FreeMoCap."""
    preparation = entry.get("preparation", {})
    session = entry.get("session", {})
    if preparation.get("status") != "prepared":
        return {"status": "not_run", "reason": f"preparation_status:{preparation.get('status', 'missing')}"}
    if session.get("status") != "session_ready":
        return {"status": "not_run", "reason": f"session_status:{session.get('status', 'missing')}"}

    started = time.monotonic()
    prepared = Path(preparation["output_path"]).resolve(strict=True)
    work_root = Path(output_root).resolve() / "work"
    if not prepared.parent.parent.parent.parent.is_relative_to(work_root):
        raise VerificationError("Prepared artifact is outside the configured work directory.")
    prepared_hash = sha256_file(prepared)
    if prepared_hash != preparation.get("output_sha256"):
        raise VerificationError("Prepared artifact hash does not match preparation manifest.")
    recording = Path(session["recording_path"]).resolve(strict=True)
    layout = validate_recording_layout(recording, prepared_hash)
    prepared_inspection = inspector(prepared)
    session_video = Path(layout["video"])
    session_inspection = inspector(session_video)
    source_inspection = entry.get("inspection", {})

    source_frames = source_inspection.get("decoded_frame_count")
    prepared_frames = prepared_inspection.get("decoded_frame_count")
    frame_count_matches = (
        source_frames is not None and prepared_frames is not None
        and source_frames == prepared_frames
    )
    source_duration = _duration_seconds(source_inspection)
    prepared_duration = _duration_seconds(prepared_inspection)
    duration_delta = (
        abs(source_duration - prepared_duration)
        if source_duration is not None and prepared_duration is not None else None
    )
    # A small container timestamp difference is expected after encoding. The
    # tolerance is recorded with the result instead of hidden in a score.
    duration_tolerance = max(0.05, 1 / _fps_value(source_inspection))
    duration_matches = duration_delta is not None and duration_delta <= duration_tolerance
    prepared_decodable = prepared_inspection.get("validation", {}).get("decodable") is True
    session_decodable = session_inspection.get("validation", {}).get("decodable") is True
    warnings = prepared_inspection.get("validation", {}).get("warnings", [])
    checks = {
        "prepared_hash_matches": True,
        "recording_layout": layout,
        "prepared_decodable": prepared_decodable,
        "session_video_decodable": session_decodable,
        "frame_count_matches_source": frame_count_matches,
        "source_frame_count": source_frames,
        "prepared_frame_count": prepared_frames,
        "duration_matches_source": duration_matches,
        "source_duration_seconds": source_duration,
        "prepared_duration_seconds": prepared_duration,
        "duration_delta_seconds": duration_delta,
        "duration_tolerance_seconds": duration_tolerance,
        "prepared_warnings": warnings,
        "visual_quality_validated": False,
        "linguistic_quality_validated": False,
    }
    structural_ok = prepared_decodable and session_decodable and layout["video_count"] == 1
    status = "pass" if structural_ok and frame_count_matches and duration_matches and not warnings else "review"
    if not structural_ok:
        status = "fail"
    result = {
        "status": status, "checked_at": utc_now(), "checks": checks,
        "prepared_inspection": prepared_inspection,
        "session_inspection": session_inspection,
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }
    write_json_atomic(prepared.parent.parent / "verification.json", result)
    return result


def verify_inventory(
    report: dict[str, Any], *, inspector: Callable[[Path], dict[str, Any]],
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Verify all sessions in a report and preserve per-entry failures."""
    report["stage"] = "verify"
    counts: dict[str, int] = {}
    total = len(report["entries"])
    for index, entry in enumerate(report["entries"], start=1):
        try:
            result = verify_entry(entry, inspector=inspector, output_root=Path(report["output"]))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            result = {"status": "fail", "reason": str(error)}
        entry["verification"] = result
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if progress_callback is not None:
            progress_callback(index, total, entry)
    report["verification_summary"] = counts
    report["verification_scope"] = {
        "technical_checks": "automated media and session checks",
        "visual_quality_validated": False,
        "linguistic_quality_validated": False,
    }
    report["finished_at"] = utc_now()
    return report


def verification_exit_code(report: dict[str, Any]) -> int:
    """Return 0 only when every input passed all technical checks."""
    summary = report.get("verification_summary", {})
    entries = report.get("entries", [])
    if not entries or summary.get("pass") != len(entries):
        return 2
    return 0
