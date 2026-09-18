import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.ingestion.contracts import validate_paths
from src.ingestion.inventory import build_inventory
from src.ingestion.probe import (
    MediaError, MediaInspector, _json_output, _run, inspect_inventory,
    select_video_stream, timestamp_summary,
)


class MediaProbeTests(unittest.TestCase):
    def test_cadence_uses_actual_timestamps_not_declared_fps(self):
        cfr = timestamp_summary([{"pts": n} for n in (0, 33, 67, 100)], "1/1000")
        vfr = timestamp_summary([{"pts": n} for n in (0, 33, 100, 133)], "1/1000")
        self.assertEqual(cfr["cadence"], "cfr")
        self.assertEqual(vfr["cadence"], "vfr")
        self.assertEqual(vfr["frames"][2]["pts"], 100)

    def test_missing_repeated_or_short_timestamps_are_unknown(self):
        for frames in ([{}, {}], [{"pts": 0}, {"pts": 0}, {"pts": 1}], [{"pts": 0}]):
            with self.subTest(frames=frames):
                self.assertEqual(timestamp_summary(frames, "1/30")["cadence"], "unknown")
        estimated = timestamp_summary([{"best_effort_timestamp": 5}], "1/30")
        self.assertEqual(estimated["frames"][0]["timestamp_source"], "best_effort_timestamp")

    def test_stream_selection_ignores_cover_and_prefers_default(self):
        streams = [
            {"index": 0, "codec_type": "audio"},
            {"index": 1, "codec_type": "video", "disposition": {"attached_pic": 1}},
            {"index": 2, "codec_type": "video", "codec_name": "h264", "width": 20, "height": 20},
            {"index": 3, "codec_type": "video", "codec_name": "h264", "width": 20, "height": 20,
             "disposition": {"default": 1}},
        ]
        self.assertEqual(select_video_stream(streams)["index"], 3)
        with self.assertRaises(MediaError):
            select_video_stream(streams[:2])

    def test_tool_errors_timeouts_and_bad_json_are_actionable(self):
        with patch("src.ingestion.probe.subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 1)):
            with self.assertRaisesRegex(MediaError, "timed out"):
                _run(["ffprobe"], 1)
        with patch("src.ingestion.probe.subprocess.run", return_value=Mock(returncode=0, stderr="decode error", stdout="")):
            with self.assertRaisesRegex(MediaError, "decode error"):
                _run(["ffprobe"], 1)
        with patch("src.ingestion.probe._run", return_value="not json"):
            with self.assertRaisesRegex(MediaError, "invalid JSON"):
                _json_output(["ffprobe"], 1)

    def test_invalid_timeout_and_missing_tool_are_global_errors(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                MediaInspector(timeout=timeout)
        with self.assertRaisesRegex(MediaError, "Executable not found"):
            MediaInspector(ffprobe="nonexistent-ffprobe-cp12")

    def test_one_failed_inspection_does_not_stop_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input"
            source.mkdir()
            for name in ("a.mp4", "b.mp4"):
                (source / name).write_bytes(b"video")
            report = build_inventory(validate_paths(source, root / "out", directory=True))
            inspector = Mock(tools={}, timeout=1)
            inspector.inspect.side_effect = [MediaError("corrupt"), {"validation": {"warnings": []}}]
            inspect_inventory(report, inspector)
            self.assertEqual([e["status"] for e in report["entries"]], ["invalid", "valid"])
            self.assertEqual(report["entries"][1]["sha256"], hashlib.sha256(b"video").hexdigest())

    def test_mutation_during_inspection_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input"
            source.mkdir()
            video = source / "a.mp4"
            video.write_bytes(b"original")
            report = build_inventory(validate_paths(source, root / "out", directory=True))
            inspector = Mock(tools={}, timeout=1)

            def mutate(path):
                path.write_bytes(b"modified")
                return {"validation": {"warnings": []}}

            inspector.inspect.side_effect = mutate
            inspect_inventory(report, inspector)
            self.assertEqual(report["entries"][0]["status"], "invalid")
            self.assertIn("changed", report["entries"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
