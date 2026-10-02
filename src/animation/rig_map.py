"""Validate a versioned hand rig map against Blender inventory evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from src.common import sha256_file, utc_now, write_json_atomic


FINGERS = ("thumb", "index", "middle", "ring", "pinky")
SIDES = ("right", "left")


class RigMapError(ValueError):
    """A rig map is structurally incompatible with its avatar or source."""


@dataclass(frozen=True)
class RigMapResult:
    map_sha256: str
    target_armature: str
    target_bone_count: int
    source_status: str
    calibration_status: str
    mapping: dict[str, Any]


def _finger_chains(fingers: Any, *, label: str) -> dict[str, dict[str, list[str]]]:
    if not isinstance(fingers, dict) or set(fingers) != set(SIDES):
        raise RigMapError(f"{label}: são necessárias as mãos right e left.")
    seen: set[str] = set()
    for side in SIDES:
        chains = fingers[side]
        if not isinstance(chains, dict) or set(chains) != set(FINGERS):
            raise RigMapError(f"{label}.{side}: são necessários cinco dedos nomeados.")
        for finger in FINGERS:
            chain = chains[finger]
            expected = 3 if finger == "thumb" else 4
            if not isinstance(chain, list) or len(chain) != expected or not all(
                isinstance(name, str) and name for name in chain
            ):
                raise RigMapError(f"{label}.{side}.{finger}: esperados {expected} ossos nomeados.")
            for name in chain:
                if name in seen:
                    raise RigMapError(f"{label}: osso repetido no mapa: {name}")
                seen.add(name)
    return fingers


def validate_rig_map(
    map_path: Path,
    avatar_report: dict[str, Any],
    source_inventory: dict[str, Any] | None = None,
) -> RigMapResult:
    """Check both hand meshes and chains; leave real CP2/calibration explicit."""
    import yaml

    map_path = Path(map_path).resolve()
    try:
        mapping = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise RigMapError(f"Mapa do rig ilegível: {error}") from error
    if not isinstance(mapping, dict) or mapping.get("schema_version") != "1.0":
        raise RigMapError("Versão do mapa do rig não suportada.")
    if mapping.get("scope") != "hands_only_prototype":
        raise RigMapError("Escopo do mapa incompatível com o protótipo das mãos.")
    target = mapping.get("target")
    source = mapping.get("source")
    if not isinstance(target, dict) or not isinstance(source, dict):
        raise RigMapError("Mapa precisa declarar source e target.")
    if target.get("avatar_sha256") != avatar_report.get("avatar_sha256"):
        raise RigMapError("O mapa foi criado para outra versão do personagem.")
    reference_name = target.get("semantic_reference")
    if not isinstance(reference_name, str) or not reference_name or Path(reference_name).is_absolute():
        raise RigMapError("Referência anatômica relativa ausente ou inválida.")
    reference_path = (map_path.parent / reference_name).resolve()
    if not reference_path.is_relative_to(map_path.parent):
        raise RigMapError("Referência anatômica fora da pasta do mapa.")
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RigMapError(f"Referência anatômica ilegível: {error}") from error
    if (not isinstance(reference, dict) or reference.get("schema_version") != "1.0"
            or reference.get("avatar_sha256") != target["avatar_sha256"]
            or reference.get("review_status") != "visually_reviewed_for_this_avatar"):
        raise RigMapError("Referência anatômica não homologada para este avatar.")
    if target.get("armature") != reference.get("armature"):
        raise RigMapError("Armature difere da referência anatômica revisada.")
    if target.get("meshes") != reference.get("meshes"):
        raise RigMapError("Lados das malhas diferem da referência anatômica revisada.")
    if source.get("kind") != "freemocap_ajc27" or source.get("freemocap_version") != "1.8.2":
        raise RigMapError("Contrato de origem FreeMoCap incompatível.")
    motion_input = source.get("motion_input", "evaluated_cp2_rig")
    if motion_input not in {"evaluated_cp2_rig", "freemocap_hand_landmarks"}:
        raise RigMapError("Representação do movimento CP2 não suportada.")
    inventory = avatar_report.get("inventory")
    if not isinstance(inventory, dict):
        raise RigMapError("Inventário do personagem ausente.")
    rig_name = target.get("armature")
    if inventory.get("candidate_rigs") != [rig_name]:
        raise RigMapError("Armature de destino ausente ou ambígua.")
    armature = next((item for item in inventory.get("armatures", []) if item.get("name") == rig_name), None)
    if armature is None:
        raise RigMapError("Armature de destino não encontrada no inventário.")
    bones = {bone["name"]: bone for bone in armature["bones"]}
    target_chains = _finger_chains(target.get("fingers"), label="target.fingers")
    source_chains = _finger_chains(source.get("fingers"), label="source.fingers")
    if target_chains != reference.get("fingers"):
        raise RigMapError("Dedos ou lados diferem da referência anatômica revisada.")
    if target.get("hand_motion") != "grouped_root_bones":
        raise RigMapError("Estratégia de movimento global das mãos não suportada.")

    meshes = {item["name"]: item for item in inventory.get("meshes", [])}
    target_meshes = target.get("meshes")
    if not isinstance(target_meshes, dict) or set(target_meshes) != set(SIDES):
        raise RigMapError("Mapa precisa identificar as duas malhas de mãos.")
    for side in SIDES:
        mesh_name = target_meshes[side]
        mesh = meshes.get(mesh_name)
        if mesh is None or rig_name not in mesh.get("armature_modifiers", []):
            raise RigMapError(f"Malha {side} não está ligada à armature {rig_name}.")
        mapped = {name for chain in target_chains[side].values() for name in chain}
        if mapped != set(mesh.get("vertex_groups", [])):
            raise RigMapError(f"Cobertura de ossos da malha {side} incompleta ou trocada.")
        roots = []
        for finger in FINGERS:
            chain = target_chains[side][finger]
            for index, name in enumerate(chain):
                bone = bones.get(name)
                if bone is None:
                    raise RigMapError(f"Osso de destino ausente: {name}")
                expected_parent = None if index == 0 else chain[index - 1]
                if bone.get("parent") != expected_parent:
                    raise RigMapError(f"Hierarquia incorreta em {side}.{finger}: {name}")
            roots.append(bones[chain[0]])
        if any(not isinstance(root.get("head"), list) or len(root["head"]) != 3 for root in roots):
            raise RigMapError(f"Posição de repouso das raízes {side} indisponível.")
        reference = roots[0]["head"]
        if any(max(abs(a - b) for a, b in zip(root["head"], reference)) > 0.03 for root in roots):
            raise RigMapError(f"Raízes dos dedos {side} não compartilham a base da mão.")
        suffix = ".R" if side == "right" else ".L"
        if not all(name.endswith(suffix) for chain in source_chains[side].values() for name in chain):
            raise RigMapError(f"Lateralidade da origem {side} incompatível.")
        hand_bones = source.get("hand_bones")
        if not isinstance(hand_bones, dict) or hand_bones.get(side) != f"hand{suffix}":
            raise RigMapError(f"Osso global da mão {side} ausente na origem.")

    source_status = "pending_real_cp2_skeleton"
    if source_inventory is not None:
        required = {
            name for side in SIDES for chain in source_chains[side].values() for name in chain
        } | set(source["hand_bones"].values())
        source_armatures = source_inventory.get("armatures", [])
        if not any(required <= {bone["name"] for bone in item.get("bones", [])} for item in source_armatures):
            raise RigMapError("O esqueleto real do CP2 não contém os ossos exigidos pelo mapa.")
        source_status = "validated"
    calibration = mapping.get("calibration")
    if not isinstance(calibration, dict) or set(calibration) != {
        "rest_pose_alignment", "hand_scale", "coordinate_axes", "translation_origin",
        "handedness_visual_check", "reference_source_sha256"
    }:
        raise RigMapError("Contrato de calibração ausente ou com campos desconhecidos.")
    expected_calibration = {
        "rest_pose_alignment": "per_bone", "hand_scale": "median_non_thumb_rest_chain_ratio",
        "coordinate_axes": "source_x_to_target_x_source_y_to_target_z_source_z_to_negative_target_y",
        "translation_origin": "first_frame_hand_midpoint_to_target_hand_midpoint",
        "handedness_visual_check": "right_hand_is_negative_x_in_source_and_avatar",
    }
    for key, expected in expected_calibration.items():
        if key == "hand_scale" and motion_input == "freemocap_hand_landmarks":
            expected = "median_non_thumb_pose_chain_ratio"
        if key == "coordinate_axes" and calibration.get(key) == "source_z_up_to_target_z_up":
            continue
        if calibration.get(key) != expected:
            raise RigMapError(f"Calibração {key} incompatível ou ainda não homologada.")
    if motion_input == "freemocap_hand_landmarks" and calibration["coordinate_axes"] != "source_z_up_to_target_z_up":
        raise RigMapError("Pontos de mão com profundidade exigem Z vertical.")
    reference_hash = calibration.get("reference_source_sha256")
    if not isinstance(reference_hash, str) or len(reference_hash) != 64 or any(
        character not in "0123456789abcdef" for character in reference_hash
    ):
        raise RigMapError("Hash do esqueleto de referência inválido.")
    return RigMapResult(
        sha256_file(map_path), rig_name, sum(len(chain) for side in SIDES for chain in target_chains[side].values()),
        source_status, "axes_defined_from_real_cp2" if source_status == "validated" else "pending_real_cp2_skeleton", mapping,
    )


def write_rig_map_report(result: RigMapResult, avatar_report: dict[str, Any], output_dir: Path) -> Path:
    """Persist the result of a successful preflight, including its pending gates."""
    mapping = result.mapping
    destination = Path(output_dir).resolve() / "reports" / (
        f"rig-map-{avatar_report['avatar_sha256']}-{result.map_sha256}.json"
    )
    coverage = {
        side: {finger: {"source": mapping["source"]["fingers"][side][finger],
                        "target": mapping["target"]["fingers"][side][finger]}
               for finger in FINGERS}
        for side in SIDES
    }
    report = {
        "schema_version": "1.0", "stage": "rig_map_preflight",
        "status": "ready_for_retarget_prototype" if result.source_status == "validated"
                  and result.calibration_status == "axes_defined_from_real_cp2" else "pending_cp2_calibration",
        "created_at_utc": utc_now(), "avatar_sha256": avatar_report["avatar_sha256"],
        "map_sha256": result.map_sha256, "target_armature": result.target_armature,
        "semantic_reference": mapping["target"]["semantic_reference"],
        "source_status": result.source_status, "calibration_status": result.calibration_status,
        "coverage": coverage,
    }
    write_json_atomic(destination, report)
    return destination
