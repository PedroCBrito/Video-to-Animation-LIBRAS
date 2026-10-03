"""Review and promote a generated CP3 bundle without capturing/rendering again."""
import json
from pathlib import Path
from uuid import uuid4

from src.animation.delivery import record_visual_review, verified_metadata
from src.animation.retargeting import publish_animation, publish_review, verify_job_inputs
from src.application.ingestion_service import IngestionRun
from src.application.workspace import output_lock
from src.common import utc_now, write_json_atomic
from src.ingestion.contracts import write_report


def locate_review_job(path: Path) -> tuple[Path, dict]:
    selected = Path(path).resolve()
    metadata_path = selected / "metadata.json" if selected.is_dir() else selected
    selected_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    work = metadata_path.parent
    if not (work / "retarget-input.json").is_file():
        work = Path(selected_metadata["avatar_work_path"]).resolve().parent
    metadata = verified_metadata(work)
    for key in ("animation_sha256", "video_sha256", "compatibility", "run_id", "clip_id"):
        if selected_metadata.get(key) != metadata.get(key):
            raise ValueError("O pacote selecionado pertence a outra versão da animação.")
    return work, metadata


def review_animation(path: Path, review: dict, *, cancel_event=None) -> IngestionRun:
    if not isinstance(review, dict):
        raise ValueError("A revisão deve ser um objeto JSON.")
    work, initial = locate_review_job(path)
    output = Path(initial["delivery_output"])
    with output_lock(output):
        # Another frontend may have updated review between selection and locking.
        verified_metadata(work)
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Revisão cancelada.")
        job = json.loads((work / "retarget-input.json").read_text(encoding="utf-8"))
        verify_job_inputs(job)
        metadata = record_visual_review(work, review.get("status"), review.get("reviewer", ""),
                                        review.get("notes", ""), review.get("intervals", []))
        verify_job_inputs(job)
        delivered = publish_animation(work, output, metadata, cancel_event=cancel_event)
        destination = delivered or publish_review(work, output, metadata, cancel_event=cancel_event)
        result = {"status": metadata["status"], "reason": metadata["visual_review"]["notes"],
                  "animation_path": str(destination / "animation.blend"), "preview_path": str(destination / "preview.mp4"),
                  "metadata_path": str(destination / "metadata.json"), "result_path": str(destination),
                  "published_path": str(delivered) if delivered else None, "work_dir": str(work), "reused": True}
        report = {"schema_version": "1.0", "stage": "review", "batch_id": uuid4().hex,
                  "created_at": utc_now(), "output": str(output), "summary": {"total": 1, "by_status": {"valid": 1}},
                  "entries": [{"clip_id": metadata["clip_id"], "source_path": metadata.get("video_path"), "retarget": result}],
                  "retarget_summary": {metadata["status"]: 1}}
        report_path = write_report(report, output / ".pipeline")
        write_json_atomic(output / ".pipeline/state.json", {
            "schema_version": "1.0", "stage": "review", "status": metadata["status"], "execution_status": "completed",
            "result_status": metadata["status"], "progress_percent": 100, "report_path": str(report_path), "updated_at": utc_now(),
        })
        return IngestionRun(report, report_path, 0 if delivered else 2)
