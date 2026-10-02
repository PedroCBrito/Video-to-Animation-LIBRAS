"""Regression cases for real FreeMoCap array contracts."""

import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from src.extraction.evidence import generate_evidence


class NpyEvidenceTests(unittest.TestCase):
    def _recording(self, folder):
        recording = Path(folder)
        data = recording / "output_data"
        (data / "raw_data").mkdir(parents=True)
        (recording / "freemocap.json").write_text(json.dumps({"status": "completed", "run_id": "run-a"}))
        (data / "recording_parameters.json").write_text(json.dumps({
            "post_processing_parameters_model": {"max_gap_to_fill": 1},
        }))
        for part, points in (("body", 33), ("right_hand", 21), ("left_hand", 21)):
            np.save(data / f"mediapipe_{part}_3d_xyz.npy", np.ones((5, points, 3)))
        raw = np.ones((1, 5, 553, 3))
        return recording, raw, data / "raw_data/mediapipe_2dData_numCams_numFrames_numTrackedPoints_pixelXY.npy"

    def test_internal_gap_is_recorded_without_hiding_invalid_raw_points(self):
        with tempfile.TemporaryDirectory() as folder:
            recording, raw, path = self._recording(folder)
            raw[0, 2, 33:54, :] = np.nan
            np.save(path, raw)
            result = generate_evidence(recording)
            self.assertEqual(result.status, "pass")
            validity = json.loads((recording / "evidence/hand-validity.json").read_text())
            self.assertEqual(validity["hands"]["right"]["interpolated_or_missing_intervals"], [[2, 2]])
            self.assertFalse(validity["hands"]["right"]["raw_valid_landmarks_by_frame"][2][0])
            self.assertEqual(result.manifest["metrics"]["frame_count"], 5)

    def test_long_gap_or_missing_end_requires_review(self):
        for frames in ((1, 2, 3), (0,)):
            with tempfile.TemporaryDirectory() as folder:
                recording, raw, path = self._recording(folder)
                raw[0, list(frames), 54:75, :] = np.nan
                np.save(path, raw)
                self.assertEqual(generate_evidence(recording).status, "review")

    def test_processed_nan_is_not_approved(self):
        with tempfile.TemporaryDirectory() as folder:
            recording, raw, path = self._recording(folder)
            np.save(path, raw)
            hands = np.ones((5, 21, 3))
            hands[2, 0, 2] = np.nan
            np.save(recording / "output_data/mediapipe_right_hand_3d_xyz.npy", hands)
            self.assertEqual(generate_evidence(recording).status, "review")
