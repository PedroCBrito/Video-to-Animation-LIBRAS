"""Tests for the minimal FreeMoCap recording session."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from src.session import (
    SessionError,
    create_session,
    create_sessions,
    session_exit_code,
    validate_recording_layout,
)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="libras-cp14-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.prepared = self.output / "work" / "clip_a" / "run_a" / "prepared" / "video.mp4"
        self.prepared.parent.mkdir(parents=True)
        self.prepared.write_bytes(b"prepared video bytes")
        self.prepared_hash = hashlib.sha256(self.prepared.read_bytes()).hexdigest()
        self.preparation = {
            "status": "prepared", "clip_id": "clip_a", "run_id": "run_a",
            "output_path": str(self.prepared), "output_sha256": self.prepared_hash,
        }

    def test_creates_exactly_one_discoverable_video_and_manifest(self):
        manifest = create_session(self.preparation, self.output)
        recording = self.output / "work" / "clip_a" / "run_a" / "freemocap"
        video = recording / "synchronized_videos" / "camera_01.mp4"
        self.assertEqual(manifest["status"], "session_ready")
        self.assertTrue(video.is_file())
        self.assertEqual(validate_recording_layout(recording, self.prepared_hash)["video_count"], 1)
        self.assertTrue((recording / "session.json").is_file())
        self.assertTrue((recording.parent / "source.json").is_file())
        self.assertEqual(json.loads((recording / "session.json").read_text(encoding="utf-8")), manifest)
        self.assertEqual(video.read_bytes(), self.prepared.read_bytes())

    def test_reuses_matching_session_and_rejects_tampering(self):
        first = create_session(self.preparation, self.output)
        second = create_session(self.preparation, self.output)
        self.assertTrue(second["reused"])
        video = Path(first["layout"]["video"])
        video.write_bytes(b"tampered")
        with self.assertRaisesRegex(SessionError, "hash"):
            create_session(self.preparation, self.output)

    def test_incomplete_or_ambiguous_layout_is_rejected(self):
        recording = self.output / "work" / "clip_a" / "run_a" / "freemocap"
        videos = recording / "synchronized_videos"
        videos.mkdir(parents=True)
        (videos / "unexpected.mp4").write_bytes(b"one")
        (videos / "another.mp4").write_bytes(b"two")
        with self.assertRaisesRegex(SessionError, "complete session manifest"):
            create_session(self.preparation, self.output)

    def test_report_keeps_failed_preparations_isolated(self):
        report = {
            "output": str(self.output),
            "entries": [{"status": "valid", "preparation": self.preparation},
                        {"status": "review", "preparation": {"status": "not_run"}}],
        }
        result = create_sessions(report)
        self.assertEqual(result["session_summary"], {"session_ready": 1, "not_run": 1})
        self.assertEqual(result["entries"][1]["session"]["status"], "not_run")
        self.assertEqual(session_exit_code(result), 2)


FFPROBE = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
FFMPEG = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")


@unittest.skipUnless(FFPROBE and FFMPEG, "Set FFPROBE_BIN and FFMPEG_BIN for real media tests")
class SessionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="libras-cp14-cli-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "entrada"
        self.source.mkdir()
        self.video = self.source / "sinal.mp4"
        result = subprocess.run(
            [FFMPEG, "-v", "error", "-nostdin", "-f", "lavfi",
             "-i", "testsrc2=size=96x64:rate=24:duration=0.5",
             "-c:v", "mpeg4", "-q:v", "3", str(self.video)],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)

    def test_cli_session_creates_backend_discoverable_layout(self):
        output = self.root / "output"
        result = subprocess.run(
            [sys.executable, "-S", "cli.py", "--video", str(self.video),
             "--output-dir", str(output), "--until-stage", "session",
             "--ffprobe", FFPROBE, "--ffmpeg", FFMPEG],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = list((output / "reports").glob("session-*.json"))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(report["session_summary"], {"session_ready": 1})
        preparation = report["entries"][0]["preparation"]
        recording = Path(report["entries"][0]["session"]["recording_path"])
        self.assertTrue((recording / "synchronized_videos" / "camera_01.mp4").is_file())
        self.assertTrue(Path(preparation["output_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
