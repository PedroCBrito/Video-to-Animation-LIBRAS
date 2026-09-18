"""Shared, standard-library-only contracts for video ingestion."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from src.common.time import utc_now


SUPPORTED_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv"})
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class InputPaths:
    source: Path
    root: Path
    output: Path
    is_directory: bool


def validate_paths(source: Path, output: Path, *, directory: bool) -> InputPaths:
    """Validate before creating output; a nested output is excluded by discovery."""
    source = Path(source).resolve(strict=True)
    output = Path(output).resolve()
    if directory and not source.is_dir():
        raise ValueError(f"Input must be a directory: {source}")
    if not directory and not source.is_file():
        raise ValueError(f"Input must be a regular file: {source}")
    root = source if directory else source.parent
    if root == output or root.is_relative_to(output):
        raise ValueError("Output must not equal or contain the input directory.")
    if output.exists() and not output.is_dir():
        raise ValueError(f"Output must be a directory: {output}")
    return InputPaths(source, root, output, directory)


def new_report(stage: str, paths: InputPaths) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": uuid4().hex,
        "stage": stage,
        "created_at": utc_now(),
        "input": str(paths.source),
        "input_root": str(paths.root),
        "output": str(paths.output),
        "entries": [],
        "discovery_errors": [],
    }


def write_report(report: dict[str, Any], output: Path) -> Path:
    """Publish a new UTF-8 JSON report atomically; never rewrite source media."""
    folder = Path(output) / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{report['stage']}-{report['batch_id']}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=folder, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Publish with a hard link so an existing report is never overwritten.
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination
