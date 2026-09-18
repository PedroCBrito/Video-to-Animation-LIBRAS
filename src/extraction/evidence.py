"""Pose evidence, metrics and lightweight overlays for one extraction run."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.common import sha256_file, utc_now, write_json_atomic
from src.extraction.pipeline import ExtractionError, _load_json


class EvidenceError(ValueError):
    """Raised when extraction evidence cannot be associated safely."""


@dataclass(frozen=True)
class EvidenceResult:
    """Published technical evidence for one extraction manifest."""

    manifest: dict[str, Any]
    manifest_path: Path

    @property
    def status(self) -> str:
        return str(self.manifest.get("status", "fail"))


def _pose_path(recording: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        path = Path(explicit).resolve()
        return path if path.is_file() else None
    candidates = (
        recording / "output_data" / "processed_data" / "pose.json",
        recording / "output_data" / "processed_data" / "landmarks.json",
        recording / "output_data" / "raw_data" / "pose.json",
        recording / "output_data" / "pose.json",
    )
    return next((path for path in candidates if path.is_file()), None)


def _load_frames(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"Cannot read pose data {path}: {error}") from error
    if isinstance(data, list):
        return [frame for frame in data if isinstance(frame, Mapping)], {}
    if not isinstance(data, Mapping):
        raise EvidenceError("Pose data must be a list or an object containing frames.")
    frames = data.get("frames", [])
    if not isinstance(frames, list):
        raise EvidenceError("Pose data 'frames' must be a list.")
    return [frame for frame in frames if isinstance(frame, Mapping)], dict(data)


def _frame_points(frame: Mapping[str, Any]) -> list[dict[str, Any]]:
    points = frame.get("landmarks", frame.get("points", []))
    if isinstance(points, Mapping):
        points = [dict(point, name=name) if isinstance(point, Mapping) else {"name": name, "value": point}
                  for name, point in points.items()]
    if not isinstance(points, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, point in enumerate(points):
        if isinstance(point, Mapping):
            normalized.append({"name": point.get("name", str(index)), **dict(point)})
    return normalized


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metrics(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total_points = 0
    valid_points = 0
    invalid_points = 0
    frames_with_points = 0
    presence: dict[str, int] = {}
    confidence_values: list[float] = []
    for frame in frames:
        points = _frame_points(frame)
        if points:
            frames_with_points += 1
        for point in points:
            total_points += 1
            name = str(point.get("name", "unknown"))
            x = _number(point.get("x"))
            y = _number(point.get("y"))
            z = point.get("z")
            valid = x is not None and y is not None and (z is None or _number(z) is not None)
            if valid:
                valid_points += 1
                presence[name] = presence.get(name, 0) + 1
            else:
                invalid_points += 1
            confidence = _number(point.get("visibility", point.get("confidence")))
            if confidence is not None:
                confidence_values.append(confidence)
    return {
        "frame_count": len(frames),
        "frames_with_landmarks": frames_with_points,
        "frames_without_landmarks": len(frames) - frames_with_points,
        "landmark_count": total_points,
        "valid_landmarks": valid_points,
        "invalid_landmarks": invalid_points,
        "presence_by_landmark": presence,
        "confidence": {
            "count": len(confidence_values),
            "minimum": min(confidence_values) if confidence_values else None,
            "maximum": max(confidence_values) if confidence_values else None,
            "average": sum(confidence_values) / len(confidence_values) if confidence_values else None,
        },
    }


def _point_coordinates(point: Mapping[str, Any], width: int, height: int) -> tuple[float, float] | None:
    x = _number(point.get("x"))
    y = _number(point.get("y"))
    if x is None or y is None:
        return None
    if 0 <= x <= 1 and 0 <= y <= 1:
        return x * width, y * height
    return x, y


def _write_svg(path: Path, frame: Mapping[str, Any], width: int, height: int) -> None:
    circles: list[str] = []
    for point in _frame_points(frame):
        coordinates = _point_coordinates(point, width, height)
        if coordinates is None:
            continue
        x, y = coordinates
        label = str(point.get("name", "point")).replace("&", "&amp;").replace("<", "&lt;")
        circles.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" data-name="{label}" />')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#20252b"/>'
        + "".join(circles) + "</svg>\n"
    )
    path.write_text(svg, encoding="utf-8")


def _status(metrics: Mapping[str, Any]) -> tuple[str, str | None]:
    if (metrics["frame_count"] == 0 or metrics["landmark_count"] == 0
            or metrics["valid_landmarks"] == 0):
        return "fail", "Nenhum landmark válido foi encontrado nos dados de pose."
    if metrics["invalid_landmarks"] or metrics["frames_without_landmarks"]:
        return "review", "Há landmarks inválidos ou frames sem pose; revisar evidências."
    return "pass", None


def generate_evidence(
    recording: Path,
    *,
    pose_path: Path | None = None,
    sample_limit: int = 12,
    width: int = 640,
    height: int = 480,
) -> EvidenceResult:
    """Generate metrics and SVG frame overlays for a completed extraction."""
    recording = Path(recording).resolve()
    extraction_path = recording / "freemocap.json"
    try:
        extraction = _load_json(extraction_path)
    except ExtractionError as error:
        raise EvidenceError(str(error)) from error
    if extraction.get("status") != "completed":
        raise EvidenceError("Evidence requires a completed extraction manifest.")
    if sample_limit <= 0 or width <= 0 or height <= 0:
        raise ValueError("Evidence dimensions and sample limit must be positive.")

    selected_pose = _pose_path(recording, pose_path)
    output_dir = recording / "overlay"
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = recording / "evidence.json"
    if selected_pose is None:
        metrics = {"frame_count": 0, "frames_with_landmarks": 0, "frames_without_landmarks": 0,
                   "landmark_count": 0, "valid_landmarks": 0, "invalid_landmarks": 0,
                   "presence_by_landmark": {}, "confidence": {"count": 0, "minimum": None,
                   "maximum": None, "average": None}}
        status, reason = "review", "Dados de pose JSON não encontrados; formato do backend ainda precisa ser mapeado."
        pose_hash = None
        frames: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {}
    else:
        frames, metadata = _load_frames(selected_pose)
        metrics = _metrics(frames)
        status, reason = _status(metrics)
        pose_hash = sha256_file(selected_pose)

    sample_indices = list(range(min(len(frames), sample_limit)))
    overlay_files: list[str] = []
    for index in sample_indices:
        target = output_dir / f"frame-{index:06d}.svg"
        _write_svg(target, frames[index], width, height)
        overlay_files.append(target.relative_to(recording).as_posix())
    write_json_atomic(output_dir / "index.json", {
        "schema_version": "1.0", "run_id": extraction.get("run_id"),
        "frames": overlay_files, "sample_limit": sample_limit,
    })
    manifest = {
        "schema_version": "1.0", "stage": "evidence", "status": status,
        "created_at": utc_now(), "run_id": extraction.get("run_id"),
        "clip_id": extraction.get("clip_id"),
        "extraction_manifest_sha256": sha256_file(extraction_path),
        "pose_path": selected_pose.relative_to(recording).as_posix() if selected_pose else None,
        "pose_sha256": pose_hash, "source_metadata": metadata,
        "metrics": metrics, "reason": reason,
        "overlay": {"directory": "overlay", "frames": overlay_files,
                    "width": width, "height": height},
    }
    write_json_atomic(evidence_path, manifest)
    return EvidenceResult(manifest, evidence_path)
