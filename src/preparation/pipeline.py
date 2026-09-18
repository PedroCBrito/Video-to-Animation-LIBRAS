"""Orchestration for preparing inspected media into the work tree."""

import json
from pathlib import Path
import time
from typing import Any, Callable

from src.common import sha256_file, utc_now, write_json_atomic
from src.ingestion.inventory import summarize
from src.preparation.ffmpeg import PreparationError, run_ffmpeg
from src.preparation.profile import MediaPreparationProfile


def _run_id(entry: dict[str, Any], profile: MediaPreparationProfile, tool: str) -> str:
    payload = {
        "clip_id": entry["clip_id"], "source_sha256": entry["sha256"],
        "profile": profile.fingerprint(), "ffmpeg": str(tool),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    import hashlib
    return "run_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def prepare_clip(
    entry: dict[str, Any], output_root: Path, profile: MediaPreparationProfile,
    *, ffmpeg: str, validator: Callable[[Path], dict[str, Any]], timeout: float,
) -> dict[str, Any]:
    """Prepare one valid inventory entry and return its persisted manifest."""
    source = Path(entry["source_path"]).resolve(strict=True)
    if sha256_file(source) != entry["sha256"]:
        raise PreparationError("Source content changed since inspection; run ingestion again.")
    run_id = _run_id(entry, profile, ffmpeg)
    run_root = Path(output_root).resolve() / "work" / entry["clip_id"] / run_id
    prepared = run_root / "prepared" / "video.mp4"
    manifest_path = run_root / "preparation.json"
    if prepared.exists() or manifest_path.exists():
        if not (prepared.is_file() and manifest_path.is_file()):
            raise PreparationError("Preparation workspace contains an incomplete artifact.")
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (previous.get("source_sha256") != entry["sha256"]
                or previous.get("profile_fingerprint") != profile.fingerprint()):
            raise PreparationError("Existing preparation does not match this source/profile.")
        if sha256_file(prepared) != previous.get("output_sha256"):
            raise PreparationError("Existing prepared video hash does not match its manifest.")
        validation = validator(prepared)
        return {**previous, "reused": True, "validation": validation}

    started = time.monotonic()
    ffmpeg_result = run_ffmpeg(source, prepared, profile, ffmpeg=ffmpeg, timeout=timeout)
    validation = validator(prepared)
    output_hash = sha256_file(prepared)
    manifest = {
        "schema_version": "1.0", "stage": "prepare", "created_at": utc_now(),
        "clip_id": entry["clip_id"], "run_id": run_id,
        "source_path": str(source), "source_relative_path": entry["relative_path"],
        "source_sha256": entry["sha256"], "profile": profile.as_dict(),
        "profile_fingerprint": profile.fingerprint(), "ffmpeg": str(ffmpeg),
        "ffmpeg_command": ffmpeg_result["command"],
        "output_path": str(prepared), "output_sha256": output_hash,
        "output_size_bytes": ffmpeg_result["size_bytes"], "validation": validation,
        "elapsed_seconds": round(time.monotonic() - started, 6), "reused": False,
    }
    write_json_atomic(run_root / "source.json", {
        "schema_version": "1.0", "stage": "source", "created_at": utc_now(),
        "clip_id": entry["clip_id"], "source_path": str(source),
        "source_relative_path": entry["relative_path"],
        "source_sha256": entry["sha256"], "source_size_bytes": entry["size_bytes"],
        "source_mtime_ns": entry["mtime_ns"],
    })
    write_json_atomic(manifest_path, manifest)
    return manifest


def prepare_inventory(
    report: dict[str, Any], profile: MediaPreparationProfile, *, ffmpeg: str,
    validator: Callable[[Path], dict[str, Any]], timeout: float = 120,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Prepare only fully valid entries, preserving review/invalid evidence."""
    profile.validate()
    report["stage"] = "prepare"
    report["preparation_profile"] = profile.as_dict()
    report["preparation_profile_fingerprint"] = profile.fingerprint()
    counts: dict[str, int] = {}
    total = len(report["entries"])
    for index, entry in enumerate(report["entries"], start=1):
        if entry["status"] != "valid":
            result = {"status": "not_run", "reason": f"input_status:{entry['status']}"}
        else:
            try:
                result = {"status": "prepared", **prepare_clip(
                    entry, Path(report["output"]), profile, ffmpeg=ffmpeg,
                    validator=validator, timeout=timeout,
                )}
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                result = {"status": "failed", "reason": str(error)}
        entry["preparation"] = result
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if progress_callback is not None:
            progress_callback(index, total, entry)
    report["preparation_summary"] = counts
    report["finished_at"] = utc_now()
    summarize(report)
    return report


def preparation_exit_code(report: dict[str, Any]) -> int:
    """Return 0 only when every inspected input was prepared successfully."""
    preparation = report.get("preparation_summary", {})
    if not preparation.get("prepared"):
        return 2
    if any(entry["status"] != "valid" for entry in report["entries"]):
        return 2
    if preparation.get("failed") or preparation.get("not_run"):
        return 2
    return 0
