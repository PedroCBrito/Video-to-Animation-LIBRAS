import argparse
import sys
from pathlib import Path

# Add project root directory to sys.path for relative imports
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from src.orchestrator import PipelineOrchestrator

def main():
    parser = argparse.ArgumentParser(
        description="FreeMoCap Video-to-Animation: Converts 2D sign language videos into 3D animations using FreeMoCap and Blender."
    )
    parser.add_argument(
        "--video", "-v",
        type=str,
        required=True,
        help="Path to input video file (.mp4, .mov, .avi, .mkv)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./output",
        help="Directory where output animation and assets will be saved (default: ./output)"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to custom configuration YAML file (optional)"
    )

    args = parser.parse_args()

    video_path = Path(args.video)
    output_dir = Path(args.output_dir)
    config_path = Path(args.config) if args.config else None

    try:
        orchestrator = PipelineOrchestrator(config_path=config_path)
        orchestrator.run(video_path=video_path, output_dir=output_dir)
    except Exception as e:
        print(f"\n❌ PIPELINE ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
