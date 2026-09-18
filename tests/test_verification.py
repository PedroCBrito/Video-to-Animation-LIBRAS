"""Tests for integrated technical verification."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from src.session import create_session
from src.verification import verification_exit_code, verify_inventory
from src.verification.ingestion import verify_entry


class VerificationUnitTests(unittest.TestCase):
    def test_accepts_rational_source_fps(self):
        from src.verification.ingestion import _fps_value
        self.assertAlmostEqual(_fps_value({"fps_average": "30000/1001"}), 29.97002997)

    def test_passes_matching_decodable_preparation_and_session(self):
        with tempfile.TemporaryDirectory(prefix="libras-cp15-") as folder:
            root = Path(folder)
            output = root / "output"
            prepared = output / "work" / "clip_a" / "run_a" / "prepared" / "video.mp4"
            prepared.parent.mkdir(parents=True)
            prepared.write_bytes(b"prepared")
            import hashlib
            digest = hashlib.sha256(prepared.read_bytes()).hexdigest()
            preparation = {
                "status": "prepared", "clip_id": "clip_a", "run_id": "run_a",
                "output_path": str(prepared), "output_sha256": digest,
            }
            session = create_session(preparation, output)
            inspection = {
                "stream_duration_seconds": 1.0, "container_duration_seconds": 1.0,
                "decoded_frame_count": 30, "fps_average": "30",
                "validation": {"decodable": True, "warnings": []},
            }
            entry = {
                "status": "valid", "inspection": inspection,
                "preparation": preparation, "session": session,
            }
            result = verify_entry(entry, inspector=Mock(return_value=inspection), output_root=output)
            self.assertEqual(result["status"], "pass")
            self.assertFalse(result["checks"]["linguistic_quality_validated"])
            self.assertTrue((prepared.parent.parent / "verification.json").is_file())

    def test_review_entry_is_preserved_and_does_not_pass_batch(self):
        report = {"output": "output", "entries": [{"status": "review"}]}
        result = verify_inventory(report, inspector=Mock())
        self.assertEqual(result["verification_summary"], {"not_run": 1})
        self.assertEqual(verification_exit_code(result), 2)


FFPROBE = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
FFMPEG = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")


@unittest.skipUnless(FFPROBE and FFMPEG, "Set FFPROBE_BIN and FFMPEG_BIN for real media tests")
class VerificationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="libras-cp15-cli-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "sinal.mp4"
        result = subprocess.run(
            [FFMPEG, "-v", "error", "-nostdin", "-f", "lavfi",
             "-i", "testsrc2=size=96x64:rate=24:duration=0.5",
             "-c:v", "mpeg4", "-q:v", "3", str(self.video)],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)

    def test_cli_verify_runs_all_cp1_stages_and_writes_verification(self):
        output = self.root / "output"
        result = subprocess.run(
            [sys.executable, "-S", "cli.py", "--video", str(self.video),
             "--output-dir", str(output), "--until-stage", "verify",
             "--ffprobe", FFPROBE, "--ffmpeg", FFMPEG],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = list((output / "reports").glob("verify-*.json"))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(report["verification_summary"], {"pass": 1})
        verification_path = Path(report["entries"][0]["preparation"]["output_path"]).parent.parent / "verification.json"
        self.assertTrue(verification_path.is_file())


if __name__ == "__main__":
    unittest.main()
