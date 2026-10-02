"""Read-only inventory of the armatures in a Blender character file."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any, Callable

from src.common import sha256_file, utc_now, write_json_atomic
from src.integrations.process import ProcessResult, run_process
from src.integrations.runtime import backend_environment


class AvatarInventoryError(ValueError):
    """The character could not be inventoried safely."""


@dataclass(frozen=True)
class AvatarInventoryResult:
    report: dict[str, Any]
    report_path: Path


def _validate_inventory(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise AvatarInventoryError("Blender returned an unsupported avatar inventory.")
    armatures = data.get("armatures")
    if not isinstance(armatures, list) or not all(isinstance(item, dict) for item in armatures):
        raise AvatarInventoryError("Blender returned an invalid armature list.")
    for armature in armatures:
        if not isinstance(armature.get("name"), str) or not isinstance(armature.get("bones"), list):
            raise AvatarInventoryError("Blender returned an incomplete armature inventory.")
        if not isinstance(armature.get("linked_meshes"), list):
            raise AvatarInventoryError("Blender did not identify the meshes linked to the rig.")
    if not isinstance(data.get("candidate_rigs"), list) or not isinstance(data.get("actions"), list):
        raise AvatarInventoryError("Blender returned an incomplete avatar inventory.")
    return data


def inspect_avatar(
    avatar: Path,
    blender_executable: Path,
    output_dir: Path,
    *,
    timeout: float = 180,
    cancel_event: Any | None = None,
    process_runner: Callable[..., ProcessResult] = run_process,
) -> AvatarInventoryResult:
    """Run Blender headlessly and publish a verified inventory, never saving the avatar."""
    avatar = Path(avatar).resolve()
    blender_executable = Path(blender_executable).resolve()
    if not avatar.is_file() or avatar.suffix.lower() != ".blend":
        raise AvatarInventoryError(f"Arquivo .blend do personagem não encontrado: {avatar}")
    with avatar.open("rb") as stream:
        header = stream.read(7)
        if header != b"BLENDER" and not header.startswith((b"\x28\xb5\x2f\xfd", b"\x1f\x8b")):
            raise AvatarInventoryError(f"Arquivo do personagem não é um .blend válido: {avatar}")
    if not blender_executable.is_file():
        raise AvatarInventoryError(f"Executável do Blender não encontrado: {blender_executable}")

    script = Path(__file__).resolve().parents[2] / "scripts" / "blender" / "inspect_avatar.py"
    if not script.is_file():
        raise AvatarInventoryError(f"Script de inventário do personagem não encontrado: {script}")
    avatar_hash = sha256_file(avatar)
    reports = Path(output_dir).resolve() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    destination = reports / f"avatar-{avatar_hash}.json"
    with tempfile.TemporaryDirectory(prefix="avatar-inspect-", dir=reports) as folder:
        raw_path = Path(folder) / "inventory.json"
        command = (
            str(blender_executable), "--background", "--factory-startup",
            "--python-exit-code", "1", "--python", str(script), "--", str(avatar), str(raw_path),
        )
        result = process_runner(command, cwd=Path(folder), timeout=timeout, cancel_event=cancel_event,
                                env=backend_environment(reports.parent / "runtime"))
        if result.cancelled:
            raise AvatarInventoryError("Inspeção do personagem cancelada.")
        if result.timed_out:
            raise AvatarInventoryError("Inspeção do personagem excedeu o tempo limite.")
        if not result.succeeded:
            detail = (result.stderr or result.stdout).strip()[-1200:]
            raise AvatarInventoryError(f"Blender não conseguiu inspecionar o personagem: {detail}")
        if not raw_path.is_file():
            raise AvatarInventoryError("Blender terminou sem produzir o inventário do personagem.")
        try:
            inventory = _validate_inventory(json.loads(raw_path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise AvatarInventoryError(f"Inventário do Blender ilegível: {error}") from error
        if sha256_file(avatar) != avatar_hash:
            raise AvatarInventoryError("O arquivo do personagem mudou durante a inspeção.")

    candidates = inventory["candidate_rigs"]
    rig_status = "identified" if len(candidates) == 1 else "missing" if not candidates else "ambiguous"
    report = {
        "schema_version": "1.0",
        "stage": "avatar_inventory",
        "status": "completed",
        "created_at_utc": utc_now(),
        "avatar_path": str(avatar),
        "avatar_sha256": avatar_hash,
        "blender_executable": str(blender_executable),
        "process": {"returncode": result.returncode, "elapsed_seconds": result.elapsed_seconds},
        "rig_status": rig_status,
        "candidate_rig": candidates[0] if len(candidates) == 1 else None,
        "semantic_coverage": "pending_review",
        "inventory": inventory,
    }
    write_json_atomic(destination, report)
    return AvatarInventoryResult(report, destination)
