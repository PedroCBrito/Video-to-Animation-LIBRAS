"""Tests for profile validation, staging and FFmpeg output."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from src.ingestion.contracts import validate_paths
from src.ingestion.inventory import build_inventory
from src.ingestion.probe import MediaInspector, inspect_inventory
from src.preparation.ffmpeg import build_command
from src.preparation.pipeline import prepare_inventory, preparation_exit_code
from src.preparation.profile import MediaPreparationProfile, ProfileError, load_profile


FFPROBE = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
FFMPEG = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")


class PreparationUnitTests(unittest.TestCase):
    def test_profile_requires_target_fps_for_cfr(self):
        with self.assertRaises(ProfileError):
            MediaPreparationProfile(fps_mode="cfr").validate()
        profile = MediaPreparationProfile(fps_mode="cfr", target_fps="30/1")
        self.assertEqual(profile.as_dict()["target_fps"], "30/1")

    def test_profile_rejects_unsupported_output_and_non_boolean_audio(self):
        with self.assertRaises(ProfileError):
            MediaPreparationProfile(output_container="mkv").validate()
        with self.assertRaises(ProfileError):
            MediaPreparationProfile(remove_audio="yes").validate()

    def test_command_uses_argv_and_does_not_add_shell_syntax(self):
        command = build_command(
            Path("input video.mp4"), Path("output video.mp4"), MediaPreparationProfile(),
        )
        self.assertNotIn("-vf", command)
        self.assertIn("-fps_mode", command)
        self.assertIn("passthrough", command)
        self.assertIn("-an", command)
        self.assertEqual(command[-1], "output video.mp4")

    def test_profile_file_loads_from_yaml(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.yaml"
            path.write_text(
                "schema_version: '1.0'\nname: test\nmedia:\n  fps_mode: cfr\n  target_fps: '24/1'\n",
                encoding="utf-8",
            )
            profile = load_profile(path)
            self.assertEqual(profile.name, "test")
            self.assertEqual(profile.target_fps, "24/1")

    def test_review_and_invalid_inputs_are_preserved_and_not_prepared(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input"
            source.mkdir()
            video = source / "video.mp4"
            video.write_bytes(b"video")
            report = build_inventory(validate_paths(source, root / "output", directory=True))
            report["entries"][0]["status"] = "review"
            result = prepare_inventory(
                report, MediaPreparationProfile(), ffmpeg="ffmpeg", validator=Mock(),
            )
            self.assertEqual(result["entries"][0]["preparation"]["status"], "not_run")
            self.assertEqual(result["preparation_summary"], {"not_run": 1})
            self.assertEqual(preparation_exit_code(result), 2)


@unittest.skipUnless(FFPROBE and FFMPEG, "Set FFPROBE_BIN and FFMPEG_BIN for real media tests")
class PreparationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inspector = MediaInspector(FFPROBE, FFMPEG, timeout=30)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="libras-cp13-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "entrada"
        self.source.mkdir()
        self.video = self.source / "sinal original.mp4"
        result = subprocess.run(
            [FFMPEG, "-v", "error", "-nostdin", "-f", "lavfi",
             "-i", "testsrc2=size=96x64:rate=24:duration=1",
             "-c:v", "mpeg4", "-q:v", "3", str(self.video)],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)

    def test_prepare_writes_isolated_validated_artifact_and_manifest(self):
        before = hashlib.sha256(self.video.read_bytes()).hexdigest()
        report = build_inventory(validate_paths(self.source, self.root / "output", directory=True))
        report = inspect_inventory(report, self.inspector)
        self.assertEqual(report["entries"][0]["status"], "valid")

        prepared = prepare_inventory(
            report, MediaPreparationProfile(), ffmpeg=FFMPEG,
            validator=self.inspector.inspect, timeout=30,
        )
        entry = prepared["entries"][0]
        manifest = entry["preparation"]
        output = Path(manifest["output_path"])
        self.assertEqual(manifest["status"], "prepared")
        self.assertTrue(output.is_file())
        self.assertEqual(output.parent.name, "prepared")
        self.assertEqual(output.parent.parent.parent.parent.name, "work")
        self.assertTrue((output.parent.parent / "preparation.json").is_file())
        self.assertEqual(manifest["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).hexdigest(), before)
        self.assertEqual(manifest["validation"]["validation"]["level"], "full_selected_video_decode")
        self.assertEqual(preparation_exit_code(prepared), 0)

    def test_prepare_reuses_matching_artifact_and_rejects_tampering(self):
        report = build_inventory(validate_paths(self.source, self.root / "output", directory=True))
        report = inspect_inventory(report, self.inspector)
        profile = MediaPreparationProfile()
        first = prepare_inventory(
            report, profile, ffmpeg=FFMPEG, validator=self.inspector.inspect, timeout=30,
        )
        second = prepare_inventory(
            report, profile, ffmpeg=FFMPEG, validator=self.inspector.inspect, timeout=30,
        )
        self.assertTrue(second["entries"][0]["preparation"]["reused"])
        output = Path(first["entries"][0]["preparation"]["output_path"])
        output.write_bytes(output.read_bytes() + b"tampered")
        third = prepare_inventory(
            report, profile, ffmpeg=FFMPEG, validator=self.inspector.inspect, timeout=30,
        )
        self.assertEqual(third["entries"][0]["preparation"]["status"], "failed")
        self.assertIn("hash", third["entries"][0]["preparation"]["reason"])

    def test_cli_prepare_publishes_report_and_artifact(self):
        result = subprocess.run(
            [
                os.environ.get("PYTHON", sys.executable), "-S", "cli.py",
                "--video", str(self.video), "--output-dir", str(self.root / "cli-output"),
                "--until-stage", "prepare", "--ffprobe", FFPROBE, "--ffmpeg", FFMPEG,
            ],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = list((self.root / "cli-output" / "reports").glob("prepare-*.json"))
        self.assertEqual(len(reports), 1)
        data = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(data["preparation_summary"], {"prepared": 1})
        self.assertTrue(Path(data["entries"][0]["preparation"]["output_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
