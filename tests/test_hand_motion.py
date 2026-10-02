from pathlib import Path
import unittest
import yaml

from src.animation.hand_motion import hand_motion


class HandMotionTests(unittest.TestCase):
    def fixture(self):
        mapping = yaml.safe_load((Path(__file__).parents[1] / "config/rig-map-depth.yaml").read_text())
        points = [{"name": f"{side}_hand_{i:02d}", "x": float(i + offset), "y": float(i % 3), "z": float(-i)}
                  for side, offset in (("right", 0), ("left", 30)) for i in range(21)]
        pose = {"format": "freemocap_1.8.2_mediapipe_npy", "depth_flattened": False,
                "frames": [{"frame": 0, "landmarks": points}]}
        return pose, mapping

    def test_wrist_position_and_local_depth_survive_without_body_rig_distortion(self):
        pose, mapping = self.fixture()
        sample = hand_motion(pose, mapping, 5, 5)["samples"]["5"]
        self.assertEqual(sample["hand.L"][0], [30.0, 0.0, 0.0])
        self.assertEqual(sample["palm.01.R"][1], [5.0, 2.0, -5.0])
        self.assertEqual(sample["thumb.01.R"], [[0.0, 0.0, 0.0], [2.0, 2.0, -2.0]])
        self.assertEqual(len(sample), 40)

    def test_missing_nonfinite_and_degenerate_landmarks_are_rejected(self):
        for case in ("missing", "nan", "zero"):
            with self.subTest(case=case):
                pose, mapping = self.fixture()
                if case == "missing":
                    pose["frames"][0]["landmarks"].pop()
                elif case == "nan":
                    pose["frames"][0]["landmarks"][3]["x"] = float("nan")
                else:
                    pose["frames"][0]["landmarks"][5].update(x=0.0, y=0.0, z=0.0)
                with self.assertRaises(ValueError):
                    hand_motion(pose, mapping, 0, 0)

    def test_wrong_depth_or_frame_sequence_is_rejected(self):
        pose, mapping = self.fixture()
        for bad in (dict(pose, depth_flattened=True), dict(pose, frames=[])):
            with self.assertRaises(ValueError):
                hand_motion(bad, mapping, 0, 0)
