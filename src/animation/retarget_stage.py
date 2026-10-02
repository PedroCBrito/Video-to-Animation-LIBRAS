"""Connect verified CP2 artifacts to the CP3 per-video callback."""

from pathlib import Path
from typing import Any, Callable, Mapping
import json

from src.common import sha256_file, utc_now


RetargetCallback = Callable[[Path, dict[str, Any]], Mapping[str, Any]]


def _verified_source(entry: dict[str, Any]) -> Path:
    extraction = entry.get("extraction", {})
    if extraction.get("status") != "completed":
        raise ValueError(f"CP2 não aprovado: {extraction.get('status', 'ausente')}")
    session = entry.get("session", {})
    if session.get("status") != "session_ready":
        raise ValueError("Sessão FreeMoCap não está pronta.")
    recording = Path(session["recording_path"]).resolve()
    source = extraction.get("source_skeleton", {})
    if source.get("status") != "completed" or source.get("output_path") != "source_skeleton.blend":
        raise ValueError("Manifesto do esqueleto CP2 ausente ou incompleto.")
    manifest_path = recording / "source_skeleton.json"
    if not manifest_path.is_file():
        raise ValueError("Manifesto do esqueleto CP2 não encontrado.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != source:
        raise ValueError("Manifesto do esqueleto CP2 difere do relatório da execução.")
    blend = recording / "source_skeleton.blend"
    if not blend.is_file() or sha256_file(blend) != source.get("output_sha256"):
        raise ValueError("Hash do esqueleto CP2 incompatível ou arquivo ausente.")
    if source.get("clip_id") != entry.get("clip_id") or source.get("run_id") != session.get("run_id"):
        raise ValueError("Esqueleto CP2 pertence a outro vídeo ou execução.")
    extraction_manifest = recording / "freemocap.json"
    if not extraction_manifest.is_file() or sha256_file(extraction_manifest) != source.get("extraction_manifest_sha256"):
        raise ValueError("Manifesto de extração CP2 alterado ou ausente.")
    recorded_extraction = json.loads(extraction_manifest.read_text(encoding="utf-8"))
    reported_extraction = dict(extraction.get("extraction", {}))
    recorded_extraction.pop("reused", None)
    reported_extraction.pop("reused", None)
    if recorded_extraction != reported_extraction or recorded_extraction.get("status") != "completed":
        raise ValueError("Extração CP2 difere do relatório da execução.")
    session_manifest = recording / "session.json"
    if not session_manifest.is_file() or sha256_file(session_manifest) != source.get("session_manifest_sha256"):
        raise ValueError("Manifesto da sessão CP2 alterado ou ausente.")
    evidence_path = recording / "evidence.json"
    if not evidence_path.is_file():
        raise ValueError("Evidência CP2 ausente.")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if (evidence != extraction.get("evidence") or evidence.get("status") != "pass"
            or evidence.get("extraction_manifest_sha256") != sha256_file(extraction_manifest)):
        raise ValueError("Evidência CP2 não aprovada ou incompatível.")
    return blend


def retarget_inventory(
    report: dict[str, Any],
    callback: RetargetCallback,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    report["stage"] = "retarget"
    counts: dict[str, int] = {}
    entries = report.get("entries", [])
    for index, entry in enumerate(entries, start=1):
        try:
            blend = _verified_source(entry)
            result = dict(callback(blend, entry))
            if result.get("status") not in {"completed", "review", "failed", "cancelled"}:
                raise ValueError("Retargeting retornou status desconhecido.")
        except Exception as error:
            result = {"status": "failed" if entry.get("extraction", {}).get("status") == "completed"
                      else "not_run", "reason": str(error)}
        entry["retarget"] = result
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if progress_callback:
            progress_callback(index, len(entries), entry)
    report["retarget_summary"] = counts
    report["finished_at"] = utc_now()
    return report


def retarget_exit_code(report: Mapping[str, Any]) -> int:
    total = len(report.get("entries", []))
    return 0 if total and report.get("retarget_summary", {}).get("completed") == total else 2
