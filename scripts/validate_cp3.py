"""Repeat the real CP3 reference workflow using the normal CLI/service."""

import argparse
import os
from pathlib import Path
import shutil
import sys
import json
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def reuse_snapshot(output):
    from src.common import sha256_file
    files = list((output / ".pipeline/work").rglob("source_skeleton.blend"))
    files.extend((output / ".pipeline/work").rglob("retarget-input.json"))
    files.extend((output / ".pipeline/work").rglob("animation.blend"))
    files.extend((output / ".pipeline/work").rglob("preview.mp4"))
    for kind in ("animations", "review"):
        files.extend((output / kind).rglob("animation.blend"))
        files.extend((output / kind).rglob("preview.mp4"))
    if not files:
        raise RuntimeError("Reuse validation requires an existing result")
    return {p.relative_to(output).as_posix(): {"sha256": sha256_file(p), "mtime_ns": p.stat().st_mtime_ns}
            for p in files}


def check_reuse(args, before, started):
    from src.common import sha256_file, write_json_atomic
    after = reuse_snapshot(args.output_dir)
    state = json.loads((args.output_dir / ".pipeline/state.json").read_text(encoding="utf-8"))
    report = json.loads(Path(state["report_path"]).read_text(encoding="utf-8"))
    entries = report["entries"]
    passed = before == after and bool(entries) and all(
        e["extraction"]["extraction"].get("reused") and e["extraction"].get("source_skeleton_reused")
        and e["retarget"].get("reused") for e in entries)
    evidence = {"status": "pass" if passed else "fail", "frontend": args.frontend,
                "elapsed_seconds": round(time.monotonic() - started, 3), "pipeline_result": state["result_status"],
                "files": after, "files_unchanged": before == after, "report_path": state["report_path"],
                "avatar_original_sha256": sha256_file(ROOT / "animation.blend"),
                "video_sha256": sha256_file(args.video)}
    write_json_atomic(args.output_dir / f".pipeline/reuse-{args.frontend}.json", evidence)
    if not passed:
        raise RuntimeError("Repeated execution changed artifacts or did not reuse every stage")
    print(f"Verified reuse: {args.frontend}, {len(after)} unchanged artifacts")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="retarget", choices=["extract", "retarget", "export"])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "cp3-full")
    parser.add_argument("--blender", type=Path, default=Path("D:/blender.exe"))
    parser.add_argument("--video", type=Path, default=ROOT / "Abacaxi_Articulador1.mp4")
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--depth", action="store_true", default=True)
    parser.add_argument("--flat", action="store_false", dest="depth", help="Diagnostic flattened CP2 profile")
    parser.add_argument("--basic", action="store_true", help="Use only --video/--output-dir on the normal CLI")
    parser.add_argument("--frontend", choices=["cli", "gui"], default="cli")
    parser.add_argument("--tests", action="store_true")
    parser.add_argument("--check-reuse", action="store_true", help="Require reuse without changing captured/exported/delivered artifacts")
    parser.add_argument("--test-report", type=Path, default=ROOT / "output/cp3-validation/tests.json")
    args = parser.parse_args()
    runtime = args.output_dir.resolve() / ".pipeline" / "validation-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    temporary = runtime / "temp"
    temporary.mkdir(exist_ok=True)
    os.environ.update(TMP=str(temporary), TEMP=str(temporary), PYTHONIOENCODING="utf-8")
    sys.pycache_prefix = str(runtime / "pycache")
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        packages = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Packages"
        candidates = sorted(packages.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"))
        if not candidates:
            parser.error("Provide --ffmpeg or add FFmpeg to PATH")
        ffmpeg = candidates[-1]
    ffmpeg = Path(ffmpeg).resolve()
    ffprobe = ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    os.environ.update(FFMPEG_BIN=str(ffmpeg), FFPROBE_BIN=str(ffprobe), BLENDER_BIN=str(args.blender))
    before = reuse_snapshot(args.output_dir) if args.check_reuse else None
    reuse_started = time.monotonic()
    if args.tests:
        import io
        import unittest
        from src.common import write_json_atomic
        stream = io.StringIO()
        started = time.monotonic()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT / "tests")))
        args.test_report.parent.mkdir(parents=True, exist_ok=True)
        args.test_report.with_suffix(".txt").write_text(stream.getvalue(), encoding="utf-8")
        summary = {"status": "pass" if result.wasSuccessful() else "fail", "tests": result.testsRun,
                   "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
                   "elapsed_seconds": round(time.monotonic() - started, 3), "python": sys.version,
                   "ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe)}
        write_json_atomic(args.test_report, summary)
        print(json.dumps(summary))
        return 0 if result.wasSuccessful() else 1
    if args.frontend == "gui":
        import tkinter as tk
        from unittest.mock import patch
        from src.ui.app import IngestionApp
        root = tk.Tk()
        root.withdraw()
        app = IngestionApp(root)
        app.source_var.set(str(args.video.resolve()))
        app.output_var.set(str(args.output_dir.resolve()))
        def modal_error(title, message, **kwargs):
            raise RuntimeError(f"{title}: {message}")
        try:
            with patch("src.ui.app.messagebox.showerror", side_effect=modal_error), patch("src.ui.app.messagebox.showwarning", side_effect=modal_error):
                app._start()
            if app._worker is None:
                raise RuntimeError("GUI did not start the pipeline")
            started = time.monotonic()
            while app._worker.is_alive():
                if time.monotonic() - started > 3600:
                    app._cancel()
                    raise TimeoutError("GUI validation exceeded one hour")
                root.update()
                time.sleep(0.05)
            app._drain_events()
            state = json.loads((args.output_dir / ".pipeline/state.json").read_text(encoding="utf-8"))
            if not state.get("report_path"):
                raise RuntimeError(f"GUI pipeline failed: {state}")
            report = json.loads(Path(state["report_path"]).read_text(encoding="utf-8"))
            evidence = {"frontend": "tkinter", "window": "withdrawn", "trigger": "IngestionApp._start",
                        "status_text": app.status_var.get(), "report_path": state["report_path"],
                        "retarget_summary": report.get("retarget_summary")}
            from src.common import write_json_atomic
            write_json_atomic(args.output_dir / ".pipeline/gui-validation.json", evidence)
            print(json.dumps(evidence, ensure_ascii=False))
            if before is not None:
                check_reuse(args, before, reuse_started)
            return 0 if report.get("retarget_summary") == {"completed": 1} else 2
        finally:
            root.destroy()
    from cli import main as cli_main
    if args.basic:
        code = cli_main(["--video", str(args.video), "--output-dir", str(args.output_dir)])
        if before is not None:
            check_reuse(args, before, reuse_started)
        return code
    command = [
        "--video", str(args.video), "--output-dir", str(args.output_dir), "--until-stage", args.stage,
        "--ffmpeg", str(ffmpeg), "--ffprobe", str(ffprobe),
        "--extraction-profile", str(ROOT / "config/profiles" / ("cp2-hands-depth.yaml" if args.depth else "cp2-freemocap-1.8.2.yaml")),
        "--supported-parameters", str(ROOT / "config/profiles" / ("cp2-hands-depth-supported.json" if args.depth else "cp2-freemocap-1.8.2-supported.json")),
        "--freemocap-entrypoint", "src.integrations.freemocap_backend:process_recording" if args.depth else "freemocap.core_processes.process_motion_capture_videos.process_recording_headless:process_recording_headless",
        "--freemocap-python", sys.executable, "--blender", str(args.blender),
    ]
    if not args.depth and args.stage in {"retarget", "export"}:
        command.extend(["--rig-map", str(ROOT / "config/rig-map.yaml")])
    code = cli_main(command)
    if before is not None:
        check_reuse(args, before, reuse_started)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
