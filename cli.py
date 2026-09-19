import argparse
import json
import sys
from pathlib import Path

# Add project root directory to sys.path for relative imports
sys.path.insert(0, str(Path(__file__).parent.resolve()))

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="FreeMoCap Video-to-Animation: Converts 2D sign language videos into 3D animations using FreeMoCap and Blender."
    )
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument(
        "--video", "-v",
        type=str,
        help="Path to input video file (.mp4, .mov, .avi, .mkv)"
    )
    inputs.add_argument("--input-dir", type=Path, help="Recursively inventory a video folder")
    parser.add_argument("--until-stage", required=True, choices=["inventory", "inspect", "prepare", "session", "verify", "extract"],
                        help="Run only the selected ingestion stage")
    parser.add_argument("--profile", type=Path,
                        help="Media preparation profile for prepare/session/verify")
    parser.add_argument("--extraction-profile", type=Path,
                        help="Versioned FreeMoCap extraction profile for extract")
    parser.add_argument("--supported-parameters", type=Path,
                        help="JSON contract of parameters supported by the configured FreeMoCap version")
    parser.add_argument("--freemocap-python", type=Path, default=Path(sys.executable),
                        help="Python executable used by the isolated FreeMoCap worker")
    parser.add_argument("--freemocap-entrypoint",
                        help="FreeMoCap entrypoint in module:function format")
    parser.add_argument("--blender", type=Path, default=None,
                        help="Blender executable for source skeleton export")
    parser.add_argument("--blender-script", type=Path,
                        help="Optional FreeMoCap Blender export helper script")
    parser.add_argument("--metadata-json", type=Path,
                        help="Optional explicit dataset metadata sidecar")
    parser.add_argument("--ffprobe", default="ffprobe", help="FFprobe executable name or path")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable name or path")
    parser.add_argument("--probe-timeout", type=float, default=120,
                        help="Timeout in seconds per media tool invocation (default: 120)")
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./output",
        help="Directory where output animation and assets will be saved (default: ./output)"
    )
    args = parser.parse_args(argv)

    if args.profile and args.until_stage not in {"prepare", "session", "verify"}:
        parser.error("--profile belongs to the prepare/session/verify ingestion stages")
    extraction_options = (args.extraction_profile, args.supported_parameters, args.freemocap_entrypoint, args.blender_script)
    if any(extraction_options) and args.until_stage != "extract":
        parser.error("FreeMoCap extraction options belong to the extract stage")
    if args.until_stage == "extract":
        missing = []
        if args.extraction_profile is None:
            missing.append("--extraction-profile")
        if args.supported_parameters is None:
            missing.append("--supported-parameters")
        if not args.freemocap_entrypoint:
            missing.append("--freemocap-entrypoint")
        if missing:
            parser.error("extract requires: " + ", ".join(missing))

    output_dir = Path(args.output_dir)

    try:
        from src.application import run_ingestion
        extractor = _build_extractor(args) if args.until_stage == "extract" else None

        source = args.input_dir if args.input_dir is not None else Path(args.video)
        run = run_ingestion(
            source, output_dir, args.until_stage,
            metadata_json=args.metadata_json, profile=args.profile,
            ffprobe=args.ffprobe, ffmpeg=args.ffmpeg,
            timeout=args.probe_timeout,
            extractor=extractor,
        )
        report = run.report
        print(f"Report: {run.report_path}")
        print(f"Entries: {report['summary']['total']}; {report['summary']['by_status']}")
        if args.until_stage in {"prepare", "session", "verify"}:
            print(f"Preparation: {report['preparation_summary']}")
        if args.until_stage in {"session", "verify"}:
            print(f"Sessions: {report['session_summary']}")
        if args.until_stage == "verify":
            print(f"Verification: {report['verification_summary']}")
        if args.until_stage == "extract":
            print(f"Extraction: {report['extraction_summary']}")
        return run.exit_code
    except Exception as e:
        print(f"PIPELINE ERROR: {e}", file=sys.stderr)
        return 1


def _build_extractor(args):
    """Create the CP2 callback from explicit, versioned CLI contracts."""
    from src.animation import export_source_skeleton
    from src.extraction import generate_evidence, load_extraction_profile, run_extraction
    from src.integrations.blender import BlenderExporter
    from src.integrations.freemocap import FreeMoCapAdapter

    supported_data = json.loads(args.supported_parameters.read_text(encoding="utf-8"))
    if not isinstance(supported_data, dict):
        raise ValueError("--supported-parameters must contain a JSON object.")
    profile = load_extraction_profile(args.extraction_profile, supported_data)
    adapter = FreeMoCapAdapter(
        python_executable=args.freemocap_python,
        entrypoint=args.freemocap_entrypoint,
    )
    blender_path = args.blender or Path("blender")
    exporter = BlenderExporter(blender_path, args.blender_script)

    def extract_session(recording: Path):
        extraction = run_extraction(recording, profile, adapter)
        if not extraction.succeeded:
            return {"status": extraction.manifest.get("status", "failed"), "extraction": extraction.manifest}
        evidence = generate_evidence(recording)
        skeleton = export_source_skeleton(recording, exporter)
        status = "completed"
        if not skeleton.succeeded:
            status = "failed"
        elif evidence.status != "pass":
            status = "review"
        return {
            "status": status,
            "extraction": extraction.manifest,
            "evidence": evidence.manifest,
            "source_skeleton": skeleton.manifest,
            "reason": evidence.manifest.get("reason") if evidence.status != "pass" else None,
        }

    return extract_session

if __name__ == "__main__":
    sys.exit(main())
