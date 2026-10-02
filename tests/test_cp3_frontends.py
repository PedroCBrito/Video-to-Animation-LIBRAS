from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import patch

import cli
from src.application.settings import load_tool_paths, save_tool_paths
from src.ui.app import IngestionApp
from src.ui.dependencies import discover_media


class FrontendTests(unittest.TestCase):
    def test_cli_simple_video_defaults_to_complete_shared_service(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "sign.mp4"
            video.write_bytes(b"input")
            run = SimpleNamespace(report_path=Path("report.json"), exit_code=2,
                                  report={"summary": {"total": 1, "by_status": {"valid": 1}}, "entries": [],
                                          "extraction_summary": {"completed": 1}, "retarget_summary": {"review": 1}})
            with patch("src.application.run_ingestion", return_value=run) as service, \
                    patch("src.application.backends.build_retargeter", return_value="retarget"), \
                    patch("cli._build_extractor", return_value="extract"), \
                    patch("src.ui.dependencies.discover_blender", return_value="blender.exe"), \
                    patch("src.application.settings.load_tool_paths", return_value={}):
                self.assertEqual(cli.main(["--video", str(video), "--output-dir", str(Path(folder)/"output")]), 2)
            self.assertEqual(service.call_args.args[2], "retarget")
            self.assertEqual(service.call_args.kwargs["extractor"], "extract")
            self.assertEqual(service.call_args.kwargs["retargeter"], "retarget")

    def test_tool_paths_persist_and_explicit_invalid_media_path_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tools.json"
            save_tool_paths({"BLENDER_BIN": "D:/blender.exe"}, path)
            self.assertEqual(load_tool_paths(path), {"BLENDER_BIN": "D:/blender.exe"})
            self.assertIsNone(discover_media("ffmpeg", environment={"FFMPEG_BIN": str(Path(folder)/"missing.exe")},
                                             which=lambda _: "otherwise-on-path"))

    def test_gui_review_worker_uses_same_review_service_and_cancellation(self):
        app = object.__new__(IngestionApp)
        app._events = queue.Queue()
        cancel = threading.Event()
        with patch("src.application.review_service.review_animation", return_value="reviewed") as service:
            app._review_worker(Path("metadata.json"), {"status": "review"}, cancel)
        self.assertIs(service.call_args.kwargs["cancel_event"], cancel)
        self.assertEqual(app._events.get_nowait(), ("success", "reviewed"))
