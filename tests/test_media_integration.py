"""Real media tests. Set FFPROBE_BIN and FFMPEG_BIN if they are not on PATH."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from src.ingestion.contracts import validate_paths
from src.ingestion.inventory import build_inventory, file_hash
from src.ingestion.probe import MediaError, MediaInspector, inspect_inventory


FFPROBE = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
FFMPEG = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")


@unittest.skipUnless(FFPROBE and FFMPEG, "Set FFPROBE_BIN and FFMPEG_BIN for real media tests")
class MediaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="libras-cp12-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "vídeos com espaços"
        cls.source.mkdir()
        cls.inspector = MediaInspector(FFPROBE, FFMPEG, timeout=30)
        for extension in ("mp4", "mov", "avi", "mkv"):
            cls.generate(cls.source / f"sinal.{extension}")
        cls.generate(cls.source / "variable.mp4", [
            "-vf", r"setpts=if(lt(N\,5)\,N\,5+2*(N-5))/(30*TB)", "-fps_mode", "vfr",
        ])
        cls.run_tool([
            "-display_rotation:v:0", "90", "-i", str(cls.source / "sinal.mp4"), "-c", "copy",
            str(cls.source / "rotated.mp4"),
        ])
        cls.run_tool([
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", "-c:a", "aac",
            str(cls.source / "audio-only.mp4"),
        ])
        original = (cls.source / "sinal.mp4").read_bytes()
        (cls.source / "truncated.mp4").write_bytes(original[:len(original) // 2])
        (cls.source / "corrupt.mp4").write_bytes(b"this is not a video")

    @classmethod
    def run_tool(cls, arguments):
        result = subprocess.run(
            [FFMPEG, "-v", "error", "-nostdin", *arguments],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)

    @classmethod
    def generate(cls, destination, extra=None):
        cls.run_tool([
            "-f", "lavfi", "-i", "testsrc2=size=64x48:rate=30:duration=0.6",
            *(extra or []), "-c:v", "mpeg4", "-q:v", "3", str(destination),
        ])

    def test_four_containers_full_decode_and_no_source_changes(self):
        for extension in ("mp4", "mov", "avi", "mkv"):
            with self.subTest(extension=extension):
                path = self.source / f"sinal.{extension}"
                before = file_hash(path)
                data = self.inspector.inspect(path)
                self.assertEqual((data["width"], data["height"]), (64, 48))
                self.assertEqual(data["decoded_frame_count"], 18)
                self.assertEqual(data["fps_average"], "30")
                self.assertEqual(data["timeline"]["cadence"], "cfr")
                self.assertEqual(data["validation"]["level"], "full_selected_video_decode")
                self.assertFalse(data["validation"]["visual_quality_validated"])
                self.assertEqual(file_hash(path), before)

    def test_vfr_and_rotation_are_measured(self):
        variable = self.inspector.inspect(self.source / "variable.mp4")
        self.assertEqual(variable["timeline"]["cadence"], "vfr")
        rotated = self.inspector.inspect(self.source / "rotated.mp4")
        self.assertEqual(abs(rotated["rotation_degrees"]), 90)
        self.assertEqual(rotated["rotation_source"], "display_matrix")
        self.assertIsNone(rotated["mirrored"])

    def test_corruption_truncation_and_audio_only_are_rejected(self):
        for name in ("corrupt.mp4", "truncated.mp4", "audio-only.mp4"):
            with self.subTest(name=name), self.assertRaises(MediaError):
                self.inspector.inspect(self.source / name)

    def test_batch_and_cli_isolate_invalid_inputs(self):
        output = self.root / "output"
        report = inspect_inventory(
            build_inventory(validate_paths(self.source, output, directory=True)), self.inspector,
        )
        self.assertEqual(report["summary"]["by_status"], {"invalid": 3, "valid": 6})
        result = subprocess.run([
            sys.executable, "-S", "cli.py", "--input-dir", str(self.source),
            "--output-dir", str(output), "--until-stage", "inspect",
            "--ffprobe", FFPROBE, "--ffmpeg", FFMPEG,
        ], cwd=Path(__file__).resolve().parents[1], capture_output=True,
            encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(result.returncode, 2, result.stderr)
        manifests = list((output / "reports").glob("inspect-*.json"))
        self.assertEqual(len(manifests), 1)
        saved = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(saved["summary"], report["summary"])
        self.assertIn("version", saved["tools"]["ffprobe"])


if __name__ == "__main__":
    unittest.main()
