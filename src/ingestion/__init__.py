"""Video discovery, input contracts and media inspection services."""

from src.ingestion.contracts import (
    InputPaths,
    SCHEMA_VERSION,
    SUPPORTED_EXTENSIONS,
    new_report,
    validate_paths,
    write_report,
)
from src.ingestion.inventory import (
    build_inventory,
    clip_id,
    file_hash,
    load_metadata,
    report_exit_code,
    summarize,
)
from src.ingestion.probe import MediaError, MediaInspector, inspect_inventory

__all__ = [
    "InputPaths", "SCHEMA_VERSION", "SUPPORTED_EXTENSIONS", "MediaError",
    "MediaInspector", "build_inventory", "clip_id", "file_hash", "inspect_inventory",
    "load_metadata", "new_report", "report_exit_code", "summarize", "validate_paths",
    "write_report",
]
