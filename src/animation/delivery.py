"""Verified CP3 cache and explicit visual review of an immutable animation."""
import json
from pathlib import Path

from src.common import sha256_file, utc_now, write_json_atomic

REQUIRED_ARTIFACTS = {"animation.blend", "retarget-result.json", "retarget-input.json",
                      "bake-check.json", "reopen-check.json", "preview.mp4", "preview/frames.json", "preview/index.html"}


def validate_pass_review(review: dict, start: int, end: int) -> None:
    if review.get("status") != "pass" or not all(isinstance(review.get(k), str) and review[k].strip() for k in ("reviewer", "notes")):
        raise ValueError("Aprovação visual exige responsável e observações.")
    covered = {side: set() for side in ("right", "left")}
    for interval in review.get("intervals", []):
        side, first, last = interval.get("hand"), interval.get("start"), interval.get("end")
        if (side not in covered or type(first) is not int or type(last) is not int
                or not start <= first <= last <= end or not str(interval.get("notes", "")).strip()):
            raise ValueError("Intervalo de inspeção inválido.")
        covered[side].update(range(first, last + 1))
    if any(c != set(range(start, end + 1)) for c in covered.values()):
        raise ValueError("Aprovação exige inspeção de todos os frames de ambas as mãos.")


def artifact_manifest(work: Path) -> list[dict]:
    paths = set(REQUIRED_ARTIFACTS)
    paths.update(p.relative_to(work).as_posix() for p in (work / "preview").iterdir() if p.suffix in {".png", ".jpg"})
    if (work / "hand-motion.json").is_file():
        paths.add("hand-motion.json")
    return [{"path": p, "sha256": sha256_file(work / p)} for p in sorted(paths)]


def verified_metadata(work: Path) -> dict:
    work = Path(work).resolve()
    metadata = json.loads((work / "metadata.json").read_text(encoding="utf-8"))
    job = json.loads((work / "retarget-input.json").read_text(encoding="utf-8"))
    if metadata.get("status") not in {"review", "completed"}:
        raise ValueError("Job não contém uma animação tecnicamente verificada.")
    for key in ("compatibility", "clip_id", "run_id", "video_sha256", "frame_start", "frame_end", "fps", "fps_base", "delivery_output"):
        if metadata.get(key) != job.get(key):
            raise ValueError(f"Metadata incompatível com o job: {key}.")
    artifacts = metadata.get("artifacts", [])
    if not REQUIRED_ARTIFACTS <= {a.get("path") for a in artifacts}:
        raise ValueError("Cache sem manifesto completo de artefatos.")
    for artifact in artifacts:
        path = (work / artifact["path"]).resolve()
        if not path.is_relative_to(work) or not path.is_file() or sha256_file(path) != artifact.get("sha256"):
            raise ValueError(f"Artefato do cache ausente ou alterado: {artifact['path']}.")
    if sha256_file(work / "animation.blend") != metadata.get("animation_sha256"):
        raise ValueError("Hash da animação difere da metadata.")
    reopen = json.loads((work / "reopen-check.json").read_text(encoding="utf-8"))
    if reopen != metadata.get("reopen_check") or reopen.get("status") != "pass":
        raise ValueError("Cache sem reabertura independente aprovada.")
    review = json.loads((work / "visual-review.json").read_text(encoding="utf-8"))
    if (review != metadata.get("visual_review") or review.get("animation_sha256") != metadata["animation_sha256"]
            or review.get("video_sha256") != metadata["video_sha256"]
            or (metadata["status"] == "completed" and review.get("status") != "pass")):
        raise ValueError("Revisão visual ausente, alterada ou vinculada a outra animação.")
    if metadata["status"] == "completed":
        validate_pass_review(review, metadata["frame_start"], metadata["frame_end"])
    return metadata


def record_visual_review(work: Path, status: str, reviewer: str, notes: str, intervals: list[dict]) -> dict:
    """Change only review/metadata; captured motion and baked bytes stay unchanged."""
    metadata = verified_metadata(work)
    if metadata["status"] == "completed" and status != "pass":
        raise ValueError("Uma revisão aprovada é imutável nesta etapa; use um novo job para outra versão.")
    if (status not in {"pass", "review", "fail"} or not isinstance(reviewer, str) or not reviewer.strip()
            or not isinstance(notes, str) or not notes.strip() or not isinstance(intervals, list)):
        raise ValueError("Informe status, responsável e observações da revisão visual.")
    start, end = metadata["frame_start"], metadata["frame_end"]
    covered = {side: set() for side in ("right", "left")}
    for interval in intervals:
        if not isinstance(interval, dict):
            raise ValueError("Intervalos de inspeção devem ser objetos JSON.")
        side, first, last = interval.get("hand"), interval.get("start"), interval.get("end")
        if (side not in covered or type(first) is not int or type(last) is not int
                or not start <= first <= last <= end or not str(interval.get("notes", "")).strip()):
            raise ValueError("Intervalo de inspeção inválido; informe mão, início, fim e observações.")
        covered[side].update(range(first, last + 1))
    if status == "pass" and any(c != set(range(start, end + 1)) for c in covered.values()):
        raise ValueError("Aprovação exige inspeção de todos os frames de ambas as mãos.")
    review = {"schema_version": "1.0", "status": status, "reviewer": reviewer.strip(), "notes": notes.strip(),
              "reason": notes.strip(), "reviewed_at": utc_now(), "intervals": intervals,
              "animation_sha256": metadata["animation_sha256"], "video_sha256": metadata["video_sha256"]}
    metadata["visual_review"] = review
    metadata["status"] = "completed" if status == "pass" else "review"
    write_json_atomic(work / "visual-review.json", review)
    write_json_atomic(work / "metadata.json", metadata)
    return metadata
