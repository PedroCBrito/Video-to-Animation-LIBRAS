"""Application service for the video-ingestion stages.

Frontends provide paths and options; this service owns stage ordering and
publishes one consistent report for CLI, UI and future automation clients.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from src.common import utc_now, write_json_atomic
from src.ingestion.contracts import validate_paths, write_report
from src.ingestion.inventory import build_inventory, report_exit_code
from src.ingestion.probe import MediaInspector, inspect_inventory
from src.preparation import load_profile, prepare_inventory, preparation_exit_code
from src.session import create_sessions, session_exit_code
from src.verification import verification_exit_code, verify_inventory
from src.extraction import extract_inventory, extraction_exit_code
from src.animation.retarget_stage import retarget_inventory, retarget_exit_code
from src.application.workspace import exclusive_retarget


IngestionStage = Literal["inventory", "inspect", "prepare", "session", "verify", "extract", "retarget"]
ProgressCallback = Callable[[dict[str, Any]], None]
_STAGES = ("inventory", "inspect", "prepare", "session", "verify", "extract", "retarget")


class IngestionCancelled(RuntimeError):
    """Raised when a frontend requests cancellation between pipeline stages."""


@dataclass(frozen=True)
class IngestionRun:
    """Published result returned to any frontend."""

    report: dict[str, Any]
    report_path: Path
    exit_code: int


@exclusive_retarget
def run_ingestion(
    source: Path,
    output: Path,
    stage: IngestionStage,
    *,
    metadata_json: Path | None = None,
    profile: Path | None = None,
    ffprobe: str = "ffprobe",
    ffmpeg: str = "ffmpeg",
    timeout: float = 120,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Any | None = None,
    extractor: Callable[[Path], Any] | None = None,
    retargeter: Callable[[Path, dict[str, Any]], Any] | None = None,
) -> IngestionRun:
    """Run the requested stages in order and publish the report.

    Progress is emitted at stage and entry boundaries so graphical frontends
    can remain independent of the implementation details of each stage.
    Cancellation is checked between stages; the current FFmpeg/FFprobe call is
    allowed to finish and all published artifacts remain atomic.
    """
    if stage in {"extract", "retarget"} and extractor is None:
        raise ValueError("A configured extraction callback is required for the extract stage.")
    if stage == "retarget" and retargeter is None:
        raise ValueError("A configured retarget callback is required for the retarget stage.")
    source = Path(source)
    output = Path(output)
    paths = validate_paths(source, output, directory=source.is_dir())
    workspace = paths.output / ".pipeline" if stage == "retarget" else paths.output
    selected_stages = _STAGES[:_STAGES.index(stage) + 1]
    state_path = workspace / "state.json"
    last_progress = {"stage": "inventory", "percent": 0, "message": "Iniciando."}

    def save_state(status: str, stage_name: str, percent: int, message: str, **extra: Any) -> None:
        write_json_atomic(state_path, {
            "schema_version": "1.0", "status": status, "stage": stage_name,
            "progress_percent": percent, "message": message,
            "input": str(paths.source), "output": str(paths.output),
            "updated_at": utc_now(), **extra,
        })

    def emit(stage_name: str, completed: int, message: str, *, stage_status: str = "running", **extra: Any) -> None:
        percent = round(completed / len(selected_stages) * 100)
        event = {
            "stage": stage_name, "completed_stages": completed,
            "total_stages": len(selected_stages), "progress_percent": percent,
            "message": message, "stage_status": stage_status, **extra,
        }
        last_progress.update(stage=stage_name, percent=percent, message=message)
        save_state("running", stage_name, percent, message, stage_status=stage_status, **extra)
        if progress_callback is not None:
            progress_callback(event)

    def emit_entry(stage_name: str, index: int, total: int, entry: dict[str, Any]) -> None:
        fraction = index / total if total else 1
        completed = _STAGES.index(stage_name) + fraction
        percent = round(completed / len(selected_stages) * 100)
        message = f"Vídeo processado: {entry.get('relative_path', entry.get('source_path', 'desconhecido'))}."
        if stage_name == "inspect":
            entry_status = entry.get("status")
            entry_reason = entry.get("reason")
        else:
            result_key = {"verify": "verification", "extract": "extraction"}.get(stage_name, stage_name)
            stage_result = entry.get(result_key, {})
            entry_status = stage_result.get("status")
            entry_reason = stage_result.get("reason")
        event = {
            "stage": stage_name, "completed_stages": completed,
            "total_stages": len(selected_stages), "progress_percent": percent,
            "message": message, "stage_status": "entry", "current_entry": entry.get("relative_path"),
            "entry_index": index, "entry_total": total,
            "entry_status": entry_status, "entry_reason": entry_reason,
        }
        last_progress.update(stage=stage_name, percent=percent, message=message)
        save_state("running", stage_name, percent, message,
                   stage_status="entry", current_entry=entry.get("relative_path"), entry_index=index,
                   entry_total=total, entry_status=entry_status, entry_reason=entry_reason)
        if progress_callback is not None:
            progress_callback(event)
        check_cancelled()

    def check_cancelled() -> None:
        if cancel_event is not None and cancel_event.is_set():
            save_state("cancelled", last_progress["stage"], last_progress["percent"],
                       "Processamento cancelado.", current_entry=last_progress.get("current_entry"))
            raise IngestionCancelled("Processing cancelled by the user.")

    report: dict[str, Any]
    inspector = None
    try:
        emit("inventory", 0, "Inventariando os arquivos de entrada.")
        check_cancelled()
        report = build_inventory(paths, metadata_json)
        if stage == "retarget":
            # Discover with the public output excluded, then keep all intermediates internal.
            report["delivery_output"] = str(paths.output)
            report["output"] = str(workspace)
            for entry in report["entries"]:
                namespace = getattr(extractor, "profile_fingerprint", None)
                if namespace:
                    entry["processing_namespace"] = namespace
        emit("inventory", 1, "Inventário concluído.", stage_status="completed", entries=len(report["entries"]))
        check_cancelled()
        if inspector is None and stage in {"inspect", "prepare", "session", "verify", "extract", "retarget"}:
            inspector = MediaInspector(ffprobe, ffmpeg, timeout)
        if inspector is not None:
            emit("inspect", 1, "Inspecionando vídeos com FFmpeg/FFprobe.", entries=len(report["entries"]))
            report = inspect_inventory(
                report, inspector,
                lambda index, total, entry: emit_entry("inspect", index, total, entry),
            )
            emit("inspect", 2, "Inspeção concluída.", stage_status="completed", entries=len(report["entries"]))
            check_cancelled()
        if stage in {"prepare", "session", "verify", "extract", "retarget"}:
            media_profile = load_profile(profile)
            emit("prepare", len(selected_stages[:2]), "Preparando vídeos compatíveis.", entries=len(report["entries"]))
            report = prepare_inventory(
                report, media_profile, ffmpeg=inspector.ffmpeg,
                validator=inspector.inspect, timeout=timeout,
                progress_callback=lambda index, total, entry: emit_entry("prepare", index, total, entry),
            )
            emit("prepare", len(selected_stages[:3]), "Preparação concluída.", stage_status="completed", entries=len(report["entries"]))
            check_cancelled()
        if stage in {"session", "verify", "extract", "retarget"}:
            emit("session", len(selected_stages[:3]), "Criando sessões compatíveis com FreeMoCap.", entries=len(report["entries"]))
            report = create_sessions(
                report,
                progress_callback=lambda index, total, entry: emit_entry("session", index, total, entry),
            )
            emit("session", len(selected_stages[:4]), "Sessões concluídas.", stage_status="completed", entries=len(report["entries"]))
            check_cancelled()
        if stage in {"verify", "extract", "retarget"}:
            emit("verify", len(selected_stages[:4]), "Verificando os artefatos gerados.", entries=len(report["entries"]))
            report = verify_inventory(
                report, inspector=inspector.inspect,
                progress_callback=lambda index, total, entry: emit_entry("verify", index, total, entry),
            )
            emit("verify", 5, "Verificação concluída.", stage_status="completed", entries=len(report["entries"]))
        if stage in {"extract", "retarget"}:
            emit("extract", len(selected_stages[:5]), "Executando a extração por sessão.", entries=len(report["entries"]))
            report = extract_inventory(
                report, extractor,
                progress_callback=lambda index, total, entry: emit_entry("extract", index, total, entry),
            )
            emit("extract", 6, "Extração concluída.", stage_status="completed", entries=len(report["entries"]))
            check_cancelled()
        if stage == "retarget":
            emit("retarget", 6, "Verificando vínculos CP2 e transferindo movimento.", entries=len(report["entries"]))
            report = retarget_inventory(
                report, retargeter,
                progress_callback=lambda index, total, entry: emit_entry("retarget", index, total, entry),
            )
            emit("retarget", len(selected_stages), "Retargeting concluído.", stage_status="completed", entries=len(report["entries"]))

        outcome = "completed"
        if stage == "retarget":
            summary = report.get("retarget_summary", {})
            outcome = ("failed" if any(summary.get(k) for k in ("failed", "not_run")) else
                       "cancelled" if summary.get("cancelled") else
                       "review" if summary.get("review") else "completed")
            if not report["entries"]:
                outcome = "failed"
                report["reason"] = "Nenhum vídeo compatível foi encontrado."
            report["result_status"] = outcome
        report_path = write_report(report, workspace)
        save_state(outcome, stage, 100, "Processamento concluído.", execution_status="completed",
                   result_status=outcome, report_path=str(report_path))
        if progress_callback is not None:
            progress_callback({
                "stage": stage, "completed_stages": len(selected_stages),
                "total_stages": len(selected_stages), "progress_percent": 100,
                "message": "Processamento concluído.", "stage_status": "completed",
                "report_path": str(report_path),
            })
        if stage == "prepare":
            exit_code = preparation_exit_code(report)
        elif stage == "session":
            exit_code = session_exit_code(report)
        elif stage == "verify":
            exit_code = verification_exit_code(report)
        elif stage == "extract":
            exit_code = extraction_exit_code(report)
        elif stage == "retarget":
            exit_code = retarget_exit_code(report)
        else:
            exit_code = report_exit_code(report)
        return IngestionRun(report, report_path, exit_code)
    except IngestionCancelled:
        raise
    except Exception as error:
        save_state("failed", stage, 0, "O processamento falhou.", error=str(error))
        raise
