import argparse
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
    parser.add_argument("--until-stage", required=True, choices=["inventory", "inspect", "prepare", "session", "verify"],
                        help="Run only the selected ingestion stage")
    parser.add_argument("--profile", type=Path,
                        help="Media preparation profile for prepare/session/verify")
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

    output_dir = Path(args.output_dir)

    try:
        from src.application import run_ingestion

        source = args.input_dir if args.input_dir is not None else Path(args.video)
        run = run_ingestion(
            source, output_dir, args.until_stage,
            metadata_json=args.metadata_json, profile=args.profile,
            ffprobe=args.ffprobe, ffmpeg=args.ffmpeg,
            timeout=args.probe_timeout,
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
        return run.exit_code
    except Exception as e:
        print(f"PIPELINE ERROR: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
