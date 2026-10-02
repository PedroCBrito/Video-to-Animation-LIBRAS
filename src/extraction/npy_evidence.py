"""Read the observed FreeMoCap 1.8.2 MediaPipe array contract."""

import json
from pathlib import Path

import numpy as np

from src.common import sha256_file, write_json_atomic


def _intervals(mask):
    result = []
    start = None
    for index, missing in enumerate([*mask, False]):
        if missing and start is None:
            start = index
        elif not missing and start is not None:
            result.append([start, index - 1])
            start = None
    return result


def normalize_freemocap_pose(recording: Path) -> Path | None:
    """Preserve per-hand raw validity and derive JSON without changing arrays."""
    data = recording / "output_data"
    paths = {part: data / f"mediapipe_{part}_3d_xyz.npy"
             for part in ("body", "right_hand", "left_hand")}
    if not any(path.is_file() for path in paths.values()):
        return None
    if not all(path.is_file() for path in paths.values()):
        raise ValueError("FreeMoCap output is missing body or one of the two hands.")
    arrays = {part: np.load(path, allow_pickle=False) for part, path in paths.items()}
    lengths = set()
    for part, array in arrays.items():
        points = 33 if part == "body" else 21
        if array.ndim != 3 or array.shape[1:] != (points, 3) or not len(array):
            raise ValueError(f"Invalid FreeMoCap array shape for {part}: {array.shape}")
        lengths.add(len(array))
    if len(lengths) != 1:
        raise ValueError("FreeMoCap body and hands have different frame counts.")
    count = lengths.pop()
    parameters_path = data / "recording_parameters.json"
    parameters = json.loads(parameters_path.read_text(encoding="utf-8")) if parameters_path.is_file() else {}
    max_gap = parameters.get("post_processing_parameters_model", {}).get("max_gap_to_fill")
    raw_path = data / "raw_data/mediapipe_2dData_numCams_numFrames_numTrackedPoints_pixelXY.npy"
    hand_validity = {}
    reasons = []
    if not raw_path.is_file() or not isinstance(max_gap, int) or max_gap < 0:
        reasons.append("Dados brutos ou contrato de interpolação ausentes.")
    else:
        raw = np.load(raw_path, allow_pickle=False)
        if raw.ndim != 4 or raw.shape[0] != 1 or raw.shape[1] != count or raw.shape[2] != 553 or raw.shape[3] != 3:
            raise ValueError(f"Unsupported FreeMoCap single-camera raw array: {raw.shape}")
        for side, offset in (("right", 33), ("left", 54)):
            valid = np.isfinite(raw[0, :, offset:offset + 21]).all(axis=2)
            missing_frames = ~valid.all(axis=1)
            intervals = _intervals(missing_frames.tolist())
            longest = max((end - start + 1 for start, end in intervals), default=0)
            hand_validity[side] = {
                "raw_valid_landmarks_by_frame": valid.tolist(),
                "interpolated_or_missing_intervals": intervals,
                "longest_missing_run": longest,
                "processed_all_finite": bool(np.isfinite(arrays[f"{side}_hand"]).all()),
            }
            if longest > max_gap or missing_frames[0] or missing_frames[-1]:
                reasons.append(f"{side}: lacuna excede o contrato de interpolação ou alcança uma extremidade.")
    frames = []
    for index in range(count):
        points = []
        for part, array in arrays.items():
            for joint, xyz in enumerate(array[index]):
                finite = bool(np.isfinite(xyz).all())
                points.append({"name": f"{part}_{joint:02d}",
                               **dict(zip(("x", "y", "z"), [float(v) for v in xyz] if finite else [None] * 3))})
        frames.append({"frame": index, "landmarks": points})
    evidence_dir = recording / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    validity_path = evidence_dir / "hand-validity.json"
    write_json_atomic(validity_path, {"schema_version": "1.0", "hands": hand_validity,
                                   "max_gap_to_fill": max_gap, "review_reasons": reasons})
    selected = evidence_dir / "pose.json"
    write_json_atomic(selected, {
        "schema_version": "1.0", "format": "freemocap_1.8.2_mediapipe_npy",
        "frames": frames, "technical_review_reasons": reasons,
        "raw_validity_path": validity_path.relative_to(recording).as_posix(),
        "raw_validity_sha256": sha256_file(validity_path),
        "source_arrays": [{"path": p.relative_to(recording).as_posix(), "sha256": sha256_file(p)}
                          for p in [*paths.values(), raw_path, parameters_path] if p.is_file()],
        "depth_flattened": parameters.get("anipose_triangulate_3d_parameters_model", {}).get("flatten_single_camera_data"),
        "visual_quality_validated": False, "linguistic_quality_validated": False,
    })
    return selected
