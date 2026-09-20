"""Application-stage orchestration for per-session extraction callbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from src.common import utc_now


ExtractionCallback = Callable[[Path], Mapping[str, Any]]


def extract_inventory(
    report: dict[str, Any],
    extractor: ExtractionCallback,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the configured extraction callback for every valid session.

    The callback owns backend details. This layer records one result per entry,
    so a failed session cannot be mistaken for a successful batch.
    """
    report["stage"] = "extract"
    counts: dict[str, int] = {}
    total = len(report.get("entries", []))
    for index, entry in enumerate(report.get("entries", []), start=1):
        session = entry.get("session", {})
        if session.get("status") != "session_ready":
            result: dict[str, Any] = {
                "status": "not_run",
                "reason": f"session_status:{session.get('status', 'missing')}",
            }
        else:
            try:
                recording_path = Path(session["recording_path"]).resolve()
                callback_result = extractor(recording_path)
                if not isinstance(callback_result, Mapping):
                    raise TypeError("The extraction callback must return a mapping.")
                result = dict(callback_result)
                if result.get("status") not in {"completed", "review", "failed", "cancelled"}:
                    raise ValueError("The extraction callback returned an unknown status.")
            except Exception as error:  # Preserve local failures in the batch report.
                result = {"status": "failed", "reason": str(error)}
        entry["extraction"] = result
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if progress_callback is not None:
            progress_callback(index, total, entry)
    report["extraction_summary"] = counts
    report["finished_at"] = utc_now()
    return report


def extraction_exit_code(report: Mapping[str, Any]) -> int:
    """Return 0 only when every input produced an approved extraction."""
    summary = report.get("extraction_summary", {})
    if summary.get("completed") != len(report.get("entries", [])):
        return 2
    return 0 if not any(summary.get(status) for status in ("failed", "cancelled", "review", "not_run")) else 2
