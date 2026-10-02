"""Run the CP2 extractor on an already verified CP1 FreeMoCap session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extraction import load_extraction_profile, run_extraction
from src.integrations.freemocap import FreeMoCapAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--profile", type=Path, default=Path("config/profiles/cp2-freemocap-1.8.2.yaml"))
    parser.add_argument("--supported-parameters", type=Path,
                        default=Path("config/profiles/cp2-freemocap-1.8.2-supported.json"))
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args(argv)
    supported = json.loads(args.supported_parameters.read_text(encoding="utf-8"))
    profile = load_extraction_profile(args.profile, supported)
    if not profile.entrypoint:
        parser.error("The extraction profile must declare a backend entrypoint.")
    adapter = FreeMoCapAdapter(
        python_executable=sys.executable,
        entrypoint=profile.entrypoint,
        session_argument="recording_path",
    )
    result = run_extraction(args.session, profile, adapter, timeout=args.timeout)
    print(f"Extraction status: {result.manifest['status']}")
    print(f"Manifest: {result.manifest_path}")
    if result.manifest.get("error"):
        print(result.manifest["error"], file=sys.stderr)
    return 0 if result.succeeded else 2


if __name__ == "__main__":
    raise SystemExit(main())
