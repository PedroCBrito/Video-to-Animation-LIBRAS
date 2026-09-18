"""Deterministic discovery without invoking capture or Blender."""

import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

from src.common.hashing import sha256_file
from src.ingestion.contracts import InputPaths, SUPPORTED_EXTENSIONS, new_report


def clip_id(relative_path: str) -> str:
    """Create a stable identifier from the normalized relative path."""
    import hashlib
    return "clip_" + hashlib.sha256(relative_path.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    """Return the SHA-256 digest of a media file."""
    return sha256_file(path)


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON value: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def load_metadata(path: Path | None) -> dict[str, dict[str, Any]]:
    """Explicit sidecar schema; no guesses based on dataset filenames."""
    if path is None:
        return {}
    data = json.loads(
        path.read_text(encoding="utf-8-sig"),
        parse_constant=_reject_constant, object_pairs_hook=_unique_object,
    )
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("Metadata must have schema_version '1.0'.")
    clips = data.get("clips")
    if not isinstance(clips, dict):
        raise ValueError("Metadata must contain a 'clips' object keyed by relative paths.")
    for key, value in clips.items():
        relative = PurePosixPath(key)
        if (not key or "\\" in key or ":" in key or relative.is_absolute()
                or ".." in relative.parts or relative.as_posix() != key):
            raise ValueError(f"Metadata path must be a normalized relative POSIX path: {key}")
        if not isinstance(value, dict):
            raise ValueError(f"Metadata entry must be an object: {key}")
    return clips


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def build_inventory(paths: InputPaths, metadata_path: Path | None = None) -> dict[str, Any]:
    metadata = load_metadata(metadata_path)
    metadata_source = metadata_path.resolve() if metadata_path else None
    report = new_report("inventory", paths)
    report["metadata_source"] = str(metadata_source) if metadata_source else None
    report["excluded_output"] = str(paths.output)
    candidates = []

    def discovery_error(error: OSError) -> None:
        report["discovery_errors"].append({"path": str(error.filename), "message": str(error)})

    if paths.is_directory:
        for folder, directories, files in os.walk(paths.source, onerror=discovery_error):
            parent = Path(folder)
            retained = []
            for name in sorted(directories):
                child = parent / name
                if child.resolve() == paths.output or child.resolve().is_relative_to(paths.output):
                    continue
                if _is_link(child):
                    report["discovery_errors"].append({
                        "path": str(child), "message": "Directory link/junction not traversed.",
                    })
                else:
                    retained.append(name)
            directories[:] = retained
            candidates.extend(parent / name for name in files)
    else:
        candidates = [paths.source]

    for path in sorted(candidates, key=lambda item: item.relative_to(paths.root).as_posix()):
        relative = path.relative_to(paths.root).as_posix()
        entry = {
            "clip_id": clip_id(relative), "relative_path": relative,
            "source_path": str(path), "extension": path.suffix.lower(),
            "metadata": metadata.get(relative, {}), "size_bytes": None,
            "sha256": None, "mtime_ns": None, "status": "ready", "reason": None,
        }
        try:
            if _is_link(path):
                raise ValueError("File links are not followed; provide a regular source file.")
            if not path.is_file():
                raise ValueError("Not a regular file.")
            stat = path.stat()
            entry.update(size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
            if path.resolve() == metadata_source:
                entry.update(status="skipped", reason="metadata_sidecar")
            elif path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                entry.update(status="unsupported", reason="unsupported_extension")
            elif stat.st_size == 0:
                entry.update(status="invalid", reason="empty_file")
            else:
                entry["sha256"] = file_hash(path)
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                    raise ValueError("Source changed while hashing; run inventory again.")
        except (OSError, ValueError) as error:
            entry.update(status="invalid", reason=str(error), sha256=None)
        report["entries"].append(entry)

    discovered = {entry["relative_path"] for entry in report["entries"]}
    report["unmatched_metadata"] = sorted(set(metadata) - discovered)
    summarize(report)
    return report


def summarize(report: dict[str, Any]) -> None:
    counts: dict[str, int] = {}
    for entry in report["entries"]:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    report["summary"] = {"total": len(report["entries"]), "by_status": counts}


def report_exit_code(report: dict[str, Any]) -> int:
    usable = {"ready", "valid"}
    has_usable = any(entry["status"] in usable for entry in report["entries"])
    issues = any(entry["status"] not in usable | {"skipped"} for entry in report["entries"])
    return 2 if (not has_usable or issues or report["discovery_errors"]
                 or report["unmatched_metadata"]) else 0
