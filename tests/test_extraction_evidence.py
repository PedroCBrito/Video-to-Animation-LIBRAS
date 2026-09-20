import json
from pathlib import Path
import tempfile
import unittest

from src.extraction.evidence import EvidenceError, generate_evidence


class ExtractionEvidenceTests(unittest.TestCase):
    def _recording(self, root: Path, *, pose: object | None = None, status: str = "completed") -> Path:
        recording = root / "recording"
        recording.mkdir(parents=True)
        (recording / "freemocap.json").write_text(json.dumps({
            "status": status, "run_id": "run-1", "clip_id": "clip-1",
        }), encoding="utf-8")
        if pose is not None:
            pose_path = recording / "output_data" / "processed_data" / "pose.json"
            pose_path.parent.mkdir(parents=True)
            pose_path.write_text(json.dumps(pose), encoding="utf-8")
        return recording

    def test_generates_metrics_and_svg_overlay_linked_to_run(self):
        with tempfile.TemporaryDirectory() as folder:
            recording = self._recording(Path(folder), pose={
                "fps": "30/1", "frames": [
                    {"landmarks": [{"name": "wrist", "x": 0.5, "y": 0.25, "z": 0.1, "confidence": 0.9}]},
                    {"landmarks": [{"name": "wrist", "x": 0.6, "y": 0.3, "z": 0.2, "confidence": 0.8}]},
                ],
            })
            result = generate_evidence(recording, sample_limit=1)
            saved = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            svg = recording / "overlay" / "frame-000000.svg"
            self.assertEqual(result.status, "pass")
            self.assertEqual(saved["run_id"], "run-1")
            self.assertEqual(saved["metrics"]["frame_count"], 2)
            self.assertEqual(saved["metrics"]["valid_landmarks"], 2)
            self.assertTrue(svg.is_file())

    def test_invalid_or_missing_pose_is_not_approved(self):
        with tempfile.TemporaryDirectory() as folder:
            invalid = self._recording(Path(folder), pose={"frames": [{"landmarks": [{"x": "nan", "y": 0.2}]}]})
            missing = self._recording(Path(folder) / "missing")
            invalid_result = generate_evidence(invalid)
            missing_result = generate_evidence(missing)
        self.assertEqual(invalid_result.status, "fail")
        self.assertEqual(missing_result.status, "review")
        self.assertIsNone(missing_result.manifest["pose_path"])

    def test_evidence_requires_completed_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            recording = self._recording(Path(folder), status="failed")
            with self.assertRaises(EvidenceError):
                generate_evidence(recording)

    def test_sample_limit_and_dimensions_are_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            recording = self._recording(Path(folder), pose={"frames": []})
            with self.assertRaises(ValueError):
                generate_evidence(recording, sample_limit=0)
            with self.assertRaises(ValueError):
                generate_evidence(recording, width=0)
