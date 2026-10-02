import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Add project root directory to sys.path for relative imports
sys.path.insert(0, str(Path(__file__).parent.resolve()))

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="FreeMoCap Video-to-Animation: Converts 2D sign language videos into 3D animations using FreeMoCap and Blender."
    )
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument(
        "--video", "-v",
        type=str,
        help="Path to input video file (.mp4, .mov, .avi, .mkv)"
    )
    inputs.add_argument("--input-dir", type=Path, help="Recursively inventory a video folder")
    parser.add_argument("--until-stage", choices=["inventory", "inspect", "prepare", "session", "verify", "extract", "retarget", "export"],
                        help="Stop at a stage (default: complete hands retargeting)")
    parser.add_argument("--inspect-avatar", type=Path,
                        help="Inventory the character rig in a .blend file without modifying it")
    parser.add_argument("--review-job", type=Path, help="Generated bundle or internal job to review without reprocessing")
    parser.add_argument("--review-file", type=Path, help="JSON with status, reviewer, notes and per-hand frame intervals")
    parser.add_argument("--rig-map", type=Path,
                        help="Validate a hand rig map when inspecting the avatar")
    parser.add_argument("--avatar", type=Path, help="Character used for retarget/export")
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
    parser.add_argument("--freemocap-session-argument", default="recording_path",
                        help="Session path parameter accepted by the selected FreeMoCap entrypoint")
    parser.add_argument("--blender", type=Path, default=None,
                        help="Blender executable for source skeleton export")
    parser.add_argument("--blender-script", type=Path,
                        help="Optional FreeMoCap Blender export helper script")
    parser.add_argument("--metadata-json", type=Path,
                        help="Optional explicit dataset metadata sidecar")
    parser.add_argument("--ffprobe", help="FFprobe executable name or path; discovered by default")
    parser.add_argument("--ffmpeg", help="FFmpeg executable name or path; discovered by default")
    parser.add_argument("--probe-timeout", type=float, default=120,
                        help="Timeout in seconds per media tool invocation (default: 120)")
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./output",
        help="Directory where output animation and assets will be saved (default: ./output)"
    )
    args = parser.parse_args(argv)

    if args.review_job is not None:
        if args.review_file is None or any(v is not None for v in (args.video, args.input_dir, args.inspect_avatar, args.until_stage)):
            parser.error("--review-job requires --review-file and cannot be combined with processing input")
        try:
            from src.application.review_service import review_animation
            review = json.loads(args.review_file.read_text(encoding="utf-8"))
            result = review_animation(args.review_job, review)
            print(f"Animation: {result.report['entries'][0]['retarget']['animation_path']}")
            print(f"Report: {result.report_path}")
            return result.exit_code
        except Exception as error:
            print(f"REVIEW ERROR: {error}", file=sys.stderr)
            return 1
    if args.review_file is not None:
        parser.error("--review-file requires --review-job")

    if args.inspect_avatar is not None:
        if args.video is not None or args.input_dir is not None or args.until_stage is not None:
            parser.error("--inspect-avatar cannot be combined with video input or --until-stage")
        try:
            from src.application.settings import load_tool_paths
            from src.ui.dependencies import discover_blender
            environment = {**load_tool_paths(), **os.environ}
            blender_location = args.blender or environment.get("BLENDER_BIN") or shutil.which("blender") or discover_blender()
            if not blender_location:
                raise ValueError("Blender não encontrado; configure --blender ou BLENDER_BIN.")
            from src.animation import inspect_avatar, validate_rig_map, write_rig_map_report
            internal = Path(args.output_dir) / ".pipeline"
            result = inspect_avatar(args.inspect_avatar, Path(blender_location), internal)
            print(f"Avatar inventory: {result.report_path}")
            print(f"Rig status: {result.report['rig_status']}; candidate: {result.report['candidate_rig']}")
            if args.rig_map is not None:
                rig_map = validate_rig_map(args.rig_map, result.report)
                rig_report = write_rig_map_report(rig_map, result.report, internal)
                print(f"Rig map: {rig_map.map_sha256}; {rig_map.target_bone_count} target bones")
                print(f"Rig map preflight: {rig_report}")
                print(f"Source: {rig_map.source_status}; calibration: {rig_map.calibration_status}")
            return 0
        except Exception as error:
            print(f"AVATAR INSPECTION ERROR: {error}", file=sys.stderr)
            return 1
    if args.video is None and args.input_dir is None:
        parser.error("one of --video or --input-dir is required")
    if args.until_stage is None:
        args.until_stage = "retarget"
    if args.rig_map is not None and args.until_stage not in {"retarget", "export"}:
        parser.error("--rig-map belongs to retarget/export or --inspect-avatar")

    if args.profile and args.until_stage not in {"prepare", "session", "verify", "extract", "retarget", "export"}:
        parser.error("--profile belongs to the prepare/session/verify ingestion stages")
    extraction_options = (args.extraction_profile, args.supported_parameters, args.freemocap_entrypoint, args.blender_script)
    if any(extraction_options) and args.until_stage not in {"extract", "retarget", "export"}:
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
        from src.application.settings import load_tool_paths
        from src.ui.dependencies import discover_media
        environment = {**load_tool_paths(), **os.environ}
        args.ffmpeg = args.ffmpeg or discover_media("ffmpeg", environment=environment) or "ffmpeg"
        args.ffprobe = args.ffprobe or discover_media("ffprobe", environment=environment) or "ffprobe"
        from src.application.backends import default_backend_options, build_retargeter
        retargeter = None
        if args.until_stage in {"extract", "retarget", "export"}:
            from src.ui.dependencies import discover_blender
            args.blender = args.blender or environment.get("BLENDER_BIN") or shutil.which("blender") or discover_blender()
            if not args.blender:
                raise ValueError("Blender não encontrado; configure --blender ou BLENDER_BIN.")
            args.blender = Path(args.blender)
        if args.until_stage in {"retarget", "export"}:
            defaults = default_backend_options(args.blender)
            for key in ("extraction_profile", "supported_parameters", "freemocap_entrypoint"):
                if getattr(args, key) is None:
                    setattr(args, key, getattr(defaults, key))
            retargeter = build_retargeter(args.blender, output_dir, avatar=args.avatar, rig_map=args.rig_map, ffmpeg=args.ffmpeg)
        extractor = _build_extractor(args) if args.until_stage in {"extract", "retarget", "export"} else None

        source = args.input_dir if args.input_dir is not None else Path(args.video)
        run = run_ingestion(
            source, output_dir, "retarget" if args.until_stage == "export" else args.until_stage,
            metadata_json=args.metadata_json, profile=args.profile,
            ffprobe=args.ffprobe, ffmpeg=args.ffmpeg,
            timeout=args.probe_timeout,
            extractor=extractor,
            retargeter=retargeter,
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
        if args.until_stage in {"extract", "retarget", "export"}:
            print(f"Extraction: {report['extraction_summary']}")
        if args.until_stage in {"retarget", "export"}:
            print(f"Retarget: {report['retarget_summary']}")
            for entry in report["entries"]:
                result = entry.get("retarget", {})
                if result.get("animation_path"):
                    print(f"Animation: {result['animation_path']}")
                    print(f"Preview: {result['preview_path']}")
        return run.exit_code
    except Exception as e:
        print(f"PIPELINE ERROR: {e}", file=sys.stderr)
        return 1


def _build_extractor(args):
    from src.application.backends import build_extractor
    return build_extractor(args)


if __name__ == "__main__":
    sys.exit(main())
