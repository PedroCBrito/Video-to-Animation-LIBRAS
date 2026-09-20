import json
from pathlib import Path
import sys
import tempfile
import unittest

from src.common import sha256_file
from src.extraction.pipeline import ExtractionError, run_extraction
from src.extraction.profile import resolve_extraction_profile
from src.integrations.freemocap import FreeMoCapAdapter


class ExtractionPipelineTests(unittest.TestCase):
    def _session(self, root: Path) -> Path:
        session = root / "recording"
        videos = session / "synchronized_videos"
        videos.mkdir(parents=True)
        video = videos / "camera_01.mp4"
        video.write_bytes(b"prepared")
        video_hash = sha256_file(video)
        (session / "session.json").write_text(json.dumps({
            "status": "session_ready", "clip_id": "clip-1", "run_id": "run-1",
            "prepared_sha256": video_hash, "recording_path": str(session),
        }), encoding="utf-8")
        return session

    def _profile(self):
        return resolve_extraction_profile({
            "name": "test-profile",
            "backend": {"name": "fake-freemocap", "entrypoint": "fake:process"},
            "parameters": {"model_complexity": 1},
        }, {"model_complexity": {"type": "integer", "default": 0}})

    def _adapter(self, root: Path, *, succeeds: bool = True) -> FreeMoCapAdapter:
        script = root / ("backend_success.py" if succeeds else "backend_failure.py")
        if succeeds:
            script.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "root = Path(sys.argv[1])\n"
                "(root / 'output_data' / 'raw_data').mkdir(parents=True, exist_ok=True)\n"
                "(root / 'output_data' / 'processed_data').mkdir(parents=True, exist_ok=True)\n"
                "(root / 'output_data' / 'raw_data' / 'pose.npy').write_bytes(b'raw')\n"
                "(root / 'output_data' / 'processed_data' / 'pose.npy').write_bytes(b'processed')\n"
                "print('fake backend completed')\n",
                encoding="utf-8",
            )
        else:
            script.write_text("import sys\nprint('fake backend failed', file=sys.stderr)\nsys.exit(4)\n", encoding="utf-8")
        return FreeMoCapAdapter(
            python_executable=sys.executable,
            command_template=(sys.executable, str(script), "{session_dir}"),
        )

    def test_success_preserves_outputs_logs_and_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session = self._session(root)
            result = run_extraction(session, self._profile(), self._adapter(root), timeout=10)
            saved = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            logs_exist = (session / "logs" / "stdout.log").is_file()
        self.assertTrue(result.succeeded)
        self.assertFalse(result.reused)
        self.assertTrue(saved["outputs"]["raw_data"]["exists"])
        self.assertTrue(saved["outputs"]["processed_data"]["exists"])
        self.assertGreaterEqual(len(saved["artifacts"]), 2)
        self.assertTrue(logs_exist)
        self.assertEqual(saved["status"], "completed")

    def test_matching_run_reuses_verified_artifacts_and_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session = self._session(root)
            profile = self._profile()
            first = run_extraction(session, profile, self._adapter(root), timeout=10)
            second = run_extraction(session, profile, self._adapter(root), timeout=10)
            different = resolve_extraction_profile({
                "name": "different", "parameters": {"model_complexity": 2},
            }, {"model_complexity": {"type": "integer", "default": 0}})
            with self.assertRaisesRegex(ExtractionError, "different"):
                run_extraction(session, different, self._adapter(root), timeout=10)
        self.assertTrue(first.succeeded)
        self.assertTrue(second.reused)

    def test_failed_backend_is_recorded_without_completed_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session = self._session(root)
            result = run_extraction(session, self._profile(), self._adapter(root, succeeds=False), timeout=10)
            saved = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            stderr = (session / "logs" / "stderr.log").read_text(encoding="utf-8")
        self.assertFalse(result.succeeded)
        self.assertEqual(saved["status"], "failed")
        self.assertIn("fake backend failed", stderr)

    def test_missing_session_output_is_rejected_before_backend(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session = root / "missing"
            session.mkdir()
            with self.assertRaises(ExtractionError):
                run_extraction(session, self._profile(), self._adapter(root), timeout=10)
