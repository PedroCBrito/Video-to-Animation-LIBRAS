"""Name CP2 hand landmarks for the existing rig, without a second motion solver."""
import math

LANDMARK_CHAINS = {
    "thumb": [0, 2, 3, 4],  # Three target segments; first includes the carpal.
    "index": [0, 5, 6, 7, 8],
    "middle": [0, 9, 10, 11, 12],
    "ring": [0, 13, 14, 15, 16],
    "pinky": [0, 17, 18, 19, 20],
}


def hand_motion(pose: dict, mapping: dict, start: int, end: int) -> dict:
    if pose.get("format") != "freemocap_1.8.2_mediapipe_npy" or pose.get("depth_flattened") is not False:
        raise ValueError("Movimento das mãos exige o contrato CP2 1.8.2 com profundidade.")
    frames = pose.get("frames", [])
    if len(frames) != end - start + 1 or [f.get("frame") for f in frames] != list(range(len(frames))):
        raise ValueError("Frames de pose não correspondem ao timing do esqueleto CP2.")
    samples = {}
    for frame in frames:
        points = {p["name"]: p for p in frame["landmarks"]}
        bones = {}
        for side in ("right", "left"):
            xyz = []
            for index in range(21):
                point = points.get(f"{side}_hand_{index:02d}", {})
                values = [point.get(k) for k in ("x", "y", "z")]
                if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in values):
                    raise ValueError(f"Pose CP2 inválida: {side}, ponto {index}, frame {frame['frame']}.")
                xyz.append(values)
            bones[mapping["source"]["hand_bones"][side]] = [xyz[0], xyz[9]]
            for finger, chain in LANDMARK_CHAINS.items():
                names = mapping["source"]["fingers"][side][finger]
                for name, head, tail in zip(names, chain, chain[1:]):
                    if math.dist(xyz[head], xyz[tail]) < 1e-8:
                        raise ValueError(f"Segmento degenerado: {name}, frame {frame['frame']}.")
                    bones[name] = [xyz[head], xyz[tail]]
        samples[str(start + frame["frame"])] = bones
    return {"schema_version": "1.0", "method": "cp2_hand_landmarks_image_plane_wrist_local_depth",
            "thumb_base": "wrist_to_thumb_mcp", "samples": samples}
