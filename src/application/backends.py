"""Configured backend callbacks shared by CLI and GUI."""
import json
import importlib.metadata
from pathlib import Path
import sys
from types import SimpleNamespace


def default_backend_options(blender: Path):
    root = Path(__file__).resolve().parents[2]
    return SimpleNamespace(
        extraction_profile=root / "config/profiles/cp2-hands-depth.yaml",
        supported_parameters=root / "config/profiles/cp2-hands-depth-supported.json",
        freemocap_python=Path(sys.executable), freemocap_entrypoint="src.integrations.freemocap_backend:process_recording",
        freemocap_session_argument="recording_path", blender=blender, blender_script=None,
    )


def build_extractor(args, *, cancel_event=None):
    from src.animation import export_source_skeleton
    from src.extraction import generate_evidence, load_extraction_profile, run_extraction
    from src.integrations.blender import BlenderExporter
    from src.integrations.freemocap import FreeMoCapAdapter

    supported = json.loads(args.supported_parameters.read_text(encoding="utf-8"))
    if not isinstance(supported, dict):
        raise ValueError("Supported parameters must contain a JSON object.")
    profile = load_extraction_profile(args.extraction_profile, supported)
    if profile.entrypoint and profile.entrypoint != args.freemocap_entrypoint:
        raise ValueError("Entrypoint difere do contrato do perfil de extração.")
    if profile.backend_version and Path(args.freemocap_python).resolve() == Path(sys.executable).resolve():
        installed = importlib.metadata.version(profile.backend_name)
        if installed != profile.backend_version:
            raise ValueError(f"FreeMoCap {installed} instalado; perfil exige {profile.backend_version}.")
    adapter = FreeMoCapAdapter(python_executable=args.freemocap_python, entrypoint=args.freemocap_entrypoint,
                              session_argument=args.freemocap_session_argument)
    exporter = BlenderExporter(args.blender, args.blender_script)
    def extract_session(recording):
        extraction = run_extraction(recording, profile, adapter, cancel_event=cancel_event)
        if not extraction.succeeded:
            return {"status": extraction.manifest.get("status", "failed"), "extraction": extraction.manifest}
        evidence = generate_evidence(recording)
        skeleton = export_source_skeleton(recording, exporter, cancel_event=cancel_event)
        status = ("cancelled" if skeleton.manifest.get("status") == "cancelled" else
                  "completed" if skeleton.succeeded and evidence.status == "pass" else "review" if skeleton.succeeded else "failed")
        return {"status": status, "extraction": extraction.manifest, "evidence": evidence.manifest,
                "source_skeleton": skeleton.manifest, "source_skeleton_reused": skeleton.reused,
                "reason": evidence.manifest.get("reason") if evidence.status != "pass" else None}
    extract_session.profile_fingerprint = profile.fingerprint
    return extract_session


def build_retargeter(blender, output, *, avatar=None, rig_map=None, cancel_event=None, ffmpeg="ffmpeg"):
    from src.animation.retargeting import run_retarget
    root = Path(__file__).resolve().parents[2]
    avatar = avatar or root / "animation.blend"
    rig_map = rig_map or root / "config/rig-map-depth.yaml"
    if not Path(avatar).is_file() or not Path(rig_map).is_file():
        raise ValueError("Personagem ou mapa do rig não encontrado na configuração do CP3.")
    import yaml
    from src.common import sha256_file
    mapping = yaml.safe_load(Path(rig_map).read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or mapping.get("target", {}).get("avatar_sha256") != sha256_file(Path(avatar)):
        raise ValueError("Mapa do rig não corresponde ao personagem configurado; confira a calibração do CP3.")
    return lambda source, entry: run_retarget(source, entry, avatar, rig_map, Path(blender), Path(output),
                                            cancel_event=cancel_event, ffmpeg=ffmpeg)
