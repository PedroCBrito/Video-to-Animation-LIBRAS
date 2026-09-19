import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from src.animation.source_skeleton import SourceSkeletonError, export_source_skeleton
from src.integrations.blender import BlenderExporter


class SourceSkeletonTests(unittest.TestCase):
    def _recording(self, root: Path, *, extraction_status: str = "completed") -> Path:
        recording = root / "freemocap"
        video = recording / "synchronized_videos" / "camera_01.mp4"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"synthetic prepared artifact")
        digest = hashlib.sha256(video.read_bytes()).hexdigest()
        (recording / "session.json").write_text(json.dumps({
            "status": "session_ready", "run_id": "run-1", "clip_id": "clip-1",
            "prepared_sha256": digest,
        }), encoding="utf-8")
        (recording / "freemocap.json").write_text(json.dumps({
            "status": extraction_status, "run_id": "run-1", "clip_id": "clip-1",
        }), encoding="utf-8")
        return recording

    def _exporter(self, root: Path, *, success: bool = True) -> BlenderExporter:
        script = root / "fake_blender.py"
        if success:
            script.write_text(
                "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_bytes(b'blend artifact')\nprint('exported')\n",
                encoding="utf-8",
            )
        else:
            script.write_text("import sys\nprint('failed', file=sys.stderr)\nsys.exit(4)\n", encoding="utf-8")
        return BlenderExporter(
            Path(sys.executable), script,
            command_template=("{blender}", "{script}", "{output_blend}"),
        )

    def test_exports_verified_blend_and_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recording = self._recording(root)
            result = export_source_skeleton(recording, self._exporter(root))
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            output = recording / "source_skeleton.blend"
            self.assertTrue(result.succeeded)
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(manifest["process"]["returncode"], 0)
            self.assertEqual(output.read_bytes(), b"blend artifact")
            self.assertIn("fake_blender.py", manifest["process"]["command"][1])

    def test_process_failure_is_published_without_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recording = self._recording(root)
            result = export_source_skeleton(recording, self._exporter(root, success=False))
            self.assertFalse(result.succeeded)
            self.assertEqual(result.manifest["status"], "failed")
            self.assertIn("failed", result.manifest["error"])
            self.assertFalse((recording / "source_skeleton.blend").exists())

    def test_requires_completed_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recording = self._recording(root, extraction_status="failed")
            with self.assertRaises(SourceSkeletonError):
                export_source_skeleton(recording, self._exporter(root))

    def test_command_template_is_argument_based(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exporter = self._exporter(root)
            command = exporter.build_command(root, root / "output.blend")
            self.assertEqual(command[0], sys.executable)
            self.assertEqual(command[2], str((root / "output.blend").resolve()))


if __name__ == "__main__":
    unittest.main()
