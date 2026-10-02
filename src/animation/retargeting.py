"""Traceable per-video retargeting jobs for the fixed hands avatar."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from src.animation.avatar_inventory import inspect_avatar
from src.animation.rig_map import validate_rig_map, write_rig_map_report
from src.common import sha256_file, utc_now, write_json_atomic
from src.integrations.process import run_process
from src.integrations.runtime import backend_environment


@dataclass(frozen=True)
class RetargetJob:
    work_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]


def prepare_retarget_job(source: Path, entry: dict[str, Any], avatar: Path, rig_map: Path,
                         blender: Path, output: Path, *, cancel_event=None) -> RetargetJob:
    """Check both real rigs and bind one working copy to the verified CP2 output."""
    source, avatar, rig_map = (Path(p).resolve() for p in (source, avatar, rig_map))
    if sha256_file(Path(entry["source_path"])) != entry["sha256"]:
        raise ValueError("O vídeo mudou desde o inventário.")
    internal = Path(output) / ".pipeline"
    avatar_result = inspect_avatar(avatar, blender, internal, cancel_event=cancel_event)
    source_result = inspect_avatar(source, blender, internal, cancel_event=cancel_event)
    validated = validate_rig_map(rig_map, avatar_result.report, source_result.report["inventory"])
    write_rig_map_report(validated, avatar_result.report, internal)
    mapping = validated.mapping
    evidence = entry["extraction"]["evidence"]
    motion = None
    pose_path = None
    if mapping["source"].get("motion_input") == "freemocap_hand_landmarks":
        from src.animation.hand_motion import hand_motion
        pose_path = (source.parent / evidence["pose_path"]).resolve()
        if not pose_path.is_relative_to(source.parent) or sha256_file(pose_path) != evidence["pose_sha256"]:
            raise ValueError("Pose CP2 ausente, alterada ou fora da sessão.")
        motion = hand_motion(json.loads(pose_path.read_text(encoding="utf-8")), mapping,
                             source_result.report["inventory"]["frame_start"],
                             source_result.report["inventory"]["frame_end"])
    depth = entry["extraction"].get("evidence", {}).get("source_metadata", {}).get("depth_flattened")
    expected_axes = ("source_x_to_target_x_source_y_to_target_z_source_z_to_negative_target_y" if depth is True
                     else "source_z_up_to_target_z_up" if depth is False else None)
    if expected_axes is None or mapping["calibration"]["coordinate_axes"] != expected_axes:
        raise ValueError("Eixos do mapa incompatíveis com o contrato de profundidade do CP2.")
    reference = rig_map.parent / mapping["target"]["semantic_reference"]
    compatibility = {
        "source_skeleton_sha256": sha256_file(source), "avatar_sha256": sha256_file(avatar),
        "rig_map_sha256": sha256_file(rig_map), "semantic_reference_sha256": sha256_file(reference),
        "algorithm_version": "cp3-hands-3",
        "pose_sha256": evidence.get("pose_sha256") if motion else None,
        "motion_adapter_sha256": sha256_file(Path(__file__).with_name("hand_motion.py")),
        "video_sha256": entry["sha256"],
        "preview_script_sha256": sha256_file(Path(__file__).resolve().parents[2] / "scripts/blender/preview_retarget.py"),
        "preview_builder_sha256": sha256_file(Path(__file__).with_name("preview.py")),
        "blender_version": source_result.report["inventory"]["blender_version"],
        "retarget_script_sha256": sha256_file(Path(__file__).resolve().parents[2] / "scripts/blender/retarget_hands.py"),
        "bake_script_sha256": sha256_file(Path(__file__).resolve().parents[2] / "scripts/blender/verify_bake.py"),
    }
    if compatibility["avatar_sha256"] != avatar_result.report["avatar_sha256"]:
        raise ValueError("O avatar mudou durante a preparação do retargeting.")
    if compatibility["source_skeleton_sha256"] != entry["extraction"]["source_skeleton"]["output_sha256"]:
        raise ValueError("O esqueleto CP2 mudou durante a preparação do retargeting.")
    fingerprint = hashlib.sha256(json.dumps(compatibility, sort_keys=True).encode()).hexdigest()[:20]
    work = source.parent.parent / "retarget" / fingerprint
    work.mkdir(parents=True, exist_ok=True)
    if motion:
        write_json_atomic(work / "hand-motion.json", motion)
    target_copy = work / "avatar.blend"
    if target_copy.exists():
        if sha256_file(target_copy) != compatibility["avatar_sha256"]:
            raise ValueError("Cópia de trabalho do avatar foi alterada.")
    else:
        shutil.copyfile(avatar, target_copy)
        if sha256_file(target_copy) != compatibility["avatar_sha256"]:
            raise ValueError("Cópia de trabalho do avatar não corresponde à origem.")
    inventory = source_result.report["inventory"]
    manifest = {
        "schema_version": "1.0", "stage": "retarget_input", "status": "ready",
        "created_at_utc": utc_now(), "clip_id": entry["clip_id"], "run_id": f"cp3_{fingerprint}",
        "source_run_id": entry["session"]["run_id"], "video_path": entry["source_path"],
        "video_sha256": entry["sha256"], "source_skeleton_path": str(source),
        "avatar_original_path": str(avatar), "avatar_work_path": str(target_copy),
        "rig_map_path": str(rig_map), "mapping": mapping, "compatibility": compatibility,
        "fps": inventory["fps"], "fps_base": inventory["fps_base"],
        "frame_start": inventory["frame_start"], "frame_end": inventory["frame_end"],
        "blender_version": inventory["blender_version"], "face_animation": False,
        "delivery_output": str(Path(output).resolve()),
        "cp2_evidence_path": str(source.parent / "evidence.json"),
        "cp2_evidence_sha256": sha256_file(source.parent / "evidence.json"),
        "hand_motion_path": str(work / "hand-motion.json") if motion else None,
        "hand_motion_sha256": sha256_file(work / "hand-motion.json") if motion else None,
        "cp2_pose_path": str(pose_path) if pose_path else None,
    }
    destination = work / "retarget-input.json"
    if destination.is_file():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        keys = ("compatibility", "clip_id", "video_sha256", "source_run_id", "fps", "fps_base", "frame_start", "frame_end")
        if any(previous.get(k) != manifest.get(k) for k in keys):
            raise ValueError("Job existente não corresponde às entradas atuais.")
        return RetargetJob(work, destination, previous)
    write_json_atomic(destination, manifest)
    return RetargetJob(work, destination, manifest)


def publish_animation(work: Path, output: Path, metadata: dict, *, cancel_event=None) -> Path | None:
    """Publish a checked, visually approved bundle in one directory rename."""
    if metadata.get("status") != "completed" or metadata.get("visual_review", {}).get("status") != "pass":
        return None
    if metadata.get("reopen_check", {}).get("status") != "pass":
        raise ValueError("Entrega sem verificação independente de reabertura.")
    review = metadata["visual_review"]
    from src.animation.delivery import validate_pass_review
    validate_pass_review(review, metadata["frame_start"], metadata["frame_end"])
    if (review.get("animation_sha256") != metadata.get("animation_sha256")
            or review.get("video_sha256") != metadata.get("video_sha256")):
        raise ValueError("Revisão visual pertence a outra animação ou vídeo.")
    return _publish_bundle(work, output, metadata, "animations", cancel_event=cancel_event)


def publish_review(work: Path, output: Path, metadata: dict, *, cancel_event=None) -> Path:
    if metadata.get("status") != "review" or metadata.get("reopen_check", {}).get("status") != "pass":
        raise ValueError("Pacote para revisão exige animação tecnicamente reabrível.")
    return _publish_bundle(work, output, metadata, "review", cancel_event=cancel_event)


def _publish_bundle(work: Path, output: Path, metadata: dict, kind: str, *, cancel_event=None) -> Path:
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("Publicação cancelada.")
    for key in ("clip_id", "run_id"):
        if not isinstance(metadata.get(key), str) or Path(metadata[key]).name != metadata[key] or metadata[key] in {".", ".."}:
            raise ValueError("Identidade de publicação inválida.")
    if sha256_file(work / "animation.blend") != metadata["animation_sha256"]:
        raise ValueError("Animação mudou antes da publicação.")
    if sha256_file(work / "preview.mp4") != metadata["preview_sha256"]:
        raise ValueError("Preview mudou antes da publicação.")
    parent = output / kind / metadata["clip_id"]
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / metadata["run_id"]
    if destination.exists():
        existing = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
        if (existing.get("animation_sha256") == metadata["animation_sha256"]
                and existing.get("preview_sha256") == metadata["preview_sha256"]
                and sha256_file(destination / "animation.blend") == metadata["animation_sha256"]
                and sha256_file(destination / "preview.mp4") == metadata["preview_sha256"]):
            write_json_atomic(destination / "metadata.json", metadata)
            return destination
        raise ValueError("Já existe uma entrega diferente para esta execução.")
    review_bundle = output / "review" / metadata["clip_id"] / metadata["run_id"]
    if kind == "animations" and review_bundle.is_dir():
        existing = json.loads((review_bundle / "metadata.json").read_text(encoding="utf-8"))
        if (existing.get("animation_sha256") != metadata["animation_sha256"]
                or sha256_file(review_bundle / "animation.blend") != metadata["animation_sha256"]
                or sha256_file(review_bundle / "preview.mp4") != metadata["preview_sha256"]):
            raise ValueError("Pacote de revisão foi alterado; promoção bloqueada.")
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Publicação cancelada.")
        write_json_atomic(review_bundle / "metadata.json", metadata)
        review_bundle.rename(destination)
        return destination
    # TemporaryDirectory removes only its own generated staging folder on failure.
    with tempfile.TemporaryDirectory(prefix=".publishing-", dir=parent) as folder:
        staging = Path(folder) / "bundle"
        staging.mkdir()
        shutil.copyfile(work / "animation.blend", staging / "animation.blend")
        shutil.copyfile(work / "preview.mp4", staging / "preview.mp4")
        write_json_atomic(staging / "metadata.json", metadata)
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Publicação cancelada.")
        staging.rename(destination)
    return destination


def verify_job_inputs(manifest: dict) -> None:
    """Prevent publication if an input changed during work or cache verification."""
    compatibility = manifest["compatibility"]
    inputs = [(manifest.get("avatar_original_path"), compatibility.get("avatar_sha256")),
              (manifest.get("source_skeleton_path"), compatibility.get("source_skeleton_sha256")),
              (manifest.get("rig_map_path"), compatibility.get("rig_map_sha256")),
              (manifest.get("video_path"), compatibility.get("video_sha256")),
              (manifest.get("cp2_pose_path"), compatibility.get("pose_sha256")),
              (manifest.get("cp2_evidence_path"), manifest.get("cp2_evidence_sha256")),
              (manifest.get("hand_motion_path"), manifest.get("hand_motion_sha256"))]
    if compatibility.get("semantic_reference_sha256"):
        reference = Path(manifest["rig_map_path"]).parent / manifest["mapping"]["target"]["semantic_reference"]
        inputs.append((reference, compatibility["semantic_reference_sha256"]))
    for path, expected in inputs:
        if expected is not None and (not path or not Path(path).is_file() or sha256_file(Path(path)) != expected):
            raise ValueError(f"Entrada ausente ou alterada durante o retargeting: {path}.")


def run_retarget(source: Path, entry: dict, avatar: Path, rig_map: Path, blender: Path,
                 output: Path, *, cancel_event=None, ffmpeg: str = "ffmpeg") -> dict:
    """Produce diagnostic work; publication additionally requires bound visual approval."""
    if cancel_event is not None and cancel_event.is_set():
        return {"status": "cancelled", "reason": "Retargeting cancelado antes da preparação."}
    try:
        job = prepare_retarget_job(source, entry, avatar, rig_map, blender, output, cancel_event=cancel_event)
    except Exception:
        if cancel_event is not None and cancel_event.is_set():
            return {"status": "cancelled", "reason": "Retargeting cancelado durante a preparação."}
        raise
    scripts = Path(__file__).resolve().parents[2] / "scripts/blender"
    from src.animation.delivery import artifact_manifest, verified_metadata

    def finish(metadata, reused):
        verify_job_inputs(job.manifest)
        published = publish_animation(job.work_dir, Path(output), metadata, cancel_event=cancel_event)
        review_bundle = None if published else publish_review(job.work_dir, Path(output), metadata, cancel_event=cancel_event)
        result_dir = published or review_bundle
        return {"status": metadata["status"], "reason": metadata["visual_review"].get("reason"),
                "work_dir": str(job.work_dir), "manifest_path": str(job.manifest_path),
                "preview_path": str(result_dir / "preview.mp4"), "animation_path": str(result_dir / "animation.blend"),
                "metadata_path": str(result_dir / "metadata.json"), "result_path": str(result_dir),
                "published_path": str(published) if published else None, "reused": reused}
    def execute(script, *arguments):
        result = run_process((str(blender), "--background", "--factory-startup", "--python-exit-code", "1",
                              "--python", str(scripts / script), "--", str(job.manifest_path), *arguments),
                             cwd=job.work_dir, timeout=1800, cancel_event=cancel_event,
                             env=backend_environment(Path(output) / ".pipeline" / "runtime"))
        log = job.work_dir / (Path(script).stem + ("-reopen" if arguments else "") + ".log")
        log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.cancelled:
            raise InterruptedError("Retargeting cancelado.")
        if not result.succeeded:
            raise RuntimeError(f"Blender falhou em {script}; consulte {log}")
    try:
        if (job.work_dir / "metadata.json").is_file():
            return finish(verified_metadata(job.work_dir), True)
        execute("retarget_hands.py")
        execute("preview_retarget.py")
        from src.animation.preview import create_preview, encode_preview
        create_preview(Path(entry["preparation"]["output_path"]), job.work_dir / "preview")
        compact = encode_preview(job.work_dir / "preview", ffmpeg, cancel_event=cancel_event)
        execute("verify_bake.py")
        execute("verify_bake.py", "--reopen")
        verify_job_inputs(job.manifest)
        result = json.loads((job.work_dir / "retarget-result.json").read_text(encoding="utf-8"))
        animation_hash = sha256_file(job.work_dir / "animation.blend")
        review_path = job.work_dir / "visual-review.json"
        review = {"status": "review", "reason": "Inspeção visual por mão pendente; canais finitos não aprovam qualidade visual.",
                  "animation_sha256": animation_hash, "video_sha256": entry["sha256"], "intervals": []}
        validity = json.loads((source.parent / "evidence/hand-validity.json").read_text(encoding="utf-8"))
        for hand, evidence in validity.get("hands", {}).items():
            review["intervals"].extend({"hand": hand, "start": start, "end": end,
                "notes": "Pontos brutos ausentes; intervalo interpolado no CP2."}
                for start, end in evidence.get("interpolated_or_missing_intervals", []))
        review["intervals"].extend({"hand": f["hand"], "start": f["frame"], "end": f["frame"],
                                  "notes": f["reason"]} for f in result.get("orientation_fallbacks", []))
        capture_warnings = list(review["intervals"])
        if review_path.exists():
            existing = json.loads(review_path.read_text(encoding="utf-8"))
            if (existing.get("animation_sha256") == animation_hash
                    and existing.get("video_sha256") == entry["sha256"]):
                review = existing
        write_json_atomic(review_path, review)
        reopen = json.loads((job.work_dir / "reopen-check.json").read_text(encoding="utf-8"))
        metadata = {
            **{k: v for k, v in job.manifest.items() if k not in {"mapping", "status", "stage"}},
            "stage": "retarget", "status": "completed" if review.get("status") == "pass" else "review",
            "scope": "hands_only_prototype", "action": result["action"], "hand_scale": result["hand_scale"],
            "units": "avatar_scene_units", "duration_seconds": (result["frame_end"] - result["frame_start"] + 1)
                * result["fps_base"] / result["fps"],
            "animation_sha256": animation_hash, "visual_review": review, "reopen_check": reopen,
            "linguistic_quality_validated": False,
            "preview_sha256": sha256_file(compact), "delivery_output": str(Path(output).resolve()),
            "capture_warnings": capture_warnings,
            "artifacts": artifact_manifest(job.work_dir),
        }
        write_json_atomic(job.work_dir / "metadata.json", metadata)
        return finish(metadata, False)
    except InterruptedError as error:
        return {"status": "cancelled", "reason": str(error), "work_dir": str(job.work_dir)}
