import json
from pathlib import Path
import tempfile
import unittest
import threading
from unittest.mock import patch

from src.animation.delivery import REQUIRED_ARTIFACTS, artifact_manifest, record_visual_review, verified_metadata
from src.animation.retargeting import RetargetJob, publish_animation, publish_review, run_retarget
from src.application.workspace import output_lock
from src.application.review_service import review_animation
from src.common import sha256_file, write_json_atomic


class DeliveryTests(unittest.TestCase):
    def test_cancel_before_or_during_retarget_preparation_is_not_reported_as_failure(self):
        for case in ("before", "during"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                cancel = threading.Event()
                if case == "before":
                    cancel.set()
                def interrupt(*args, **kwargs):
                    cancel.set()
                    raise ValueError("Avatar inspection interrupted")
                with patch("src.animation.retargeting.prepare_retarget_job", side_effect=interrupt) as prepare:
                    result = run_retarget(Path("source"), {}, Path("avatar"), Path("map"), Path("blender"),
                                          Path(folder), cancel_event=cancel)
                self.assertEqual(result["status"], "cancelled")
                self.assertEqual(prepare.call_count, 0 if case == "before" else 1)
                self.assertFalse((Path(folder) / "animations").exists())

    def test_cli_review_uses_same_service_and_approved_bundle_reopens_from_cache(self):
        import cli
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work, job, metadata = self.fixture(root)
            review_file = root / "inspection.json"
            write_json_atomic(review_file, {"status": "pass", "reviewer": "Test", "notes": "Controlled fixture",
                              "intervals": [{"hand": s, "start": 0, "end": 1, "notes": "Checked"} for s in ("right", "left")]})
            with patch("src.animation.retargeting.run_process") as process:
                self.assertEqual(cli.main(["--review-job", str(work), "--review-file", str(review_file)]), 0)
                process.assert_not_called()
            state = json.loads((root / ".pipeline/state.json").read_text())
            self.assertEqual(state["result_status"], "completed")
            self.assertTrue(Path(state["report_path"]).is_file())
            self.assertEqual(verified_metadata(work)["status"], "completed")

    def fixture(self, root):
        work = root / ".pipeline/work/job"
        work.mkdir(parents=True)
        for name in REQUIRED_ARTIFACTS:
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test artifact")
        job = {"compatibility": {"source": "captured"}, "clip_id": "clip-test", "run_id": "cp3-test",
               "video_sha256": "video-test", "frame_start": 0, "frame_end": 1, "fps": 30, "fps_base": 1,
               "delivery_output": str(root)}
        write_json_atomic(work / "retarget-input.json", job)
        reopen = {"status": "pass", "frame_count": 2}
        write_json_atomic(work / "reopen-check.json", reopen)
        review = {"status": "review", "animation_sha256": sha256_file(work / "animation.blend"),
                  "video_sha256": job["video_sha256"], "intervals": [], "reason": "Inspection pending"}
        write_json_atomic(work / "visual-review.json", review)
        metadata = {**job, "status": "review", "animation_sha256": review["animation_sha256"],
                    "preview_sha256": sha256_file(work / "preview.mp4"), "visual_review": review,
                    "reopen_check": reopen, "delivery_output": str(root), "artifacts": artifact_manifest(work)}
        write_json_atomic(work / "metadata.json", metadata)
        return work, job, metadata

    def test_repetition_verifies_cache_and_does_not_run_blender_or_change_animation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work, job, metadata = self.fixture(root)
            before = (work / "animation.blend").stat().st_mtime_ns
            with patch("src.animation.retargeting.prepare_retarget_job", return_value=RetargetJob(work, work / "retarget-input.json", job)), \
                    patch("src.animation.retargeting.run_process") as process:
                result = run_retarget(Path("source"), {}, Path("avatar"), Path("map"), Path("blender"), root)
                process.assert_not_called()
            self.assertTrue(result["reused"])
            self.assertIsNone(result["published_path"])
            self.assertTrue(Path(result["animation_path"]).is_file())
            self.assertEqual(before, (work / "animation.blend").stat().st_mtime_ns)

    def test_input_change_during_verification_prevents_cached_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work, job, metadata = self.fixture(root)
            video = root / "video.mp4"
            video.write_bytes(b"original video")
            job["video_path"] = str(video)
            job["compatibility"]["video_sha256"] = sha256_file(video)
            metadata.update(job)
            write_json_atomic(work / "retarget-input.json", job)
            metadata["artifacts"] = artifact_manifest(work)
            write_json_atomic(work / "metadata.json", metadata)
            video.write_bytes(b"video changed while processing")
            with patch("src.animation.retargeting.prepare_retarget_job", return_value=RetargetJob(work, work / "retarget-input.json", job)):
                with self.assertRaisesRegex(ValueError, "Entrada ausente ou alterada"):
                    run_retarget(Path("source"), {}, Path("avatar"), Path("map"), Path("blender"), root)
            self.assertFalse((root / "review").exists())
            self.assertFalse((root / "animations").exists())

    def test_review_rejects_changed_or_missing_inputs_without_recording_approval(self):
        inputs = {"video_path": "video_sha256", "avatar_original_path": "avatar_sha256",
                  "source_skeleton_path": "source_skeleton_sha256", "rig_map_path": "rig_map_sha256"}
        for path_key, hash_key in inputs.items():
            for change in ("modified", "missing"):
                with self.subTest(input=path_key, change=change), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    work, job, metadata = self.fixture(root)
                    source = root / "input"
                    source.write_bytes(b"original input")
                    job[path_key] = str(source)
                    job["compatibility"][hash_key] = sha256_file(source)
                    if path_key == "video_path":
                        job["video_sha256"] = sha256_file(source)
                        metadata["visual_review"]["video_sha256"] = job["video_sha256"]
                        write_json_atomic(work / "visual-review.json", metadata["visual_review"])
                    metadata.update(job)
                    write_json_atomic(work / "retarget-input.json", job)
                    metadata["artifacts"] = artifact_manifest(work)
                    write_json_atomic(work / "metadata.json", metadata)
                    original_metadata = (work / "metadata.json").read_bytes()
                    original_review = (work / "visual-review.json").read_bytes()
                    if change == "modified":
                        source.write_bytes(b"changed after rendering")
                    else:
                        source.unlink()
                    with self.assertRaisesRegex(ValueError, "Entrada ausente ou alterada"):
                        review_animation(work, {"status": "pass", "reviewer": "Test", "notes": "Controlled fixture",
                                               "intervals": [{"hand": side, "start": 0, "end": 1, "notes": "Checked"}
                                                             for side in ("right", "left")]})
                    self.assertEqual((work / "metadata.json").read_bytes(), original_metadata)
                    self.assertEqual((work / "visual-review.json").read_bytes(), original_review)
                    self.assertFalse((root / "animations").exists())

    def test_corrupt_missing_or_outside_artifacts_block_cache_and_publication(self):
        for case in ("changed", "missing", "outside", "timing", "stale_review"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                work, job, metadata = self.fixture(root)
                if case == "changed":
                    (work / "retarget-result.json").write_bytes(b"corrupt")
                elif case == "missing":
                    (work / "preview.mp4").unlink()
                else:
                    if case == "outside":
                        metadata["artifacts"][0]["path"] = "../../outside"
                    elif case == "timing":
                        metadata["frame_end"] = 0
                    else:
                        metadata["visual_review"]["animation_sha256"] = "other"
                    write_json_atomic(work / "metadata.json", metadata)
                with self.assertRaises(ValueError):
                    verified_metadata(work)
                self.assertFalse((root / "animations").exists())

    def test_review_requires_both_hands_and_publishes_without_reprocessing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work, job, metadata = self.fixture(root)
            original_hash = sha256_file(work / "animation.blend")
            review_bundle = publish_review(work, root, metadata)
            partial = [{"hand": "right", "start": 0, "end": 1, "notes": "Checked"}]
            with self.assertRaisesRegex(ValueError, "ambas as mãos"):
                record_visual_review(work, "pass", "Reviewer", "Controlled test", partial)
            self.assertEqual(verified_metadata(work)["status"], "review")
            complete = partial + [{"hand": "left", "start": 0, "end": 1, "notes": "Checked"}]
            updated = record_visual_review(work, "pass", "Reviewer", "Controlled test", complete)
            self.assertEqual(verified_metadata(work)["status"], "completed")
            delivered = publish_animation(work, root, updated)
            self.assertFalse(review_bundle.exists())
            self.assertEqual(sha256_file(delivered / "animation.blend"), original_hash)
            self.assertEqual(set(p.name for p in delivered.iterdir()), {"animation.blend", "preview.mp4", "metadata.json"})
            with self.assertRaises(ValueError):
                record_visual_review(work, "fail", "Reviewer", "Different version needed", complete)

    def test_output_lock_releases_after_failure_and_rejects_concurrent_writer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with output_lock(root):
                    with self.assertRaisesRegex(ValueError, "processamento"):
                        with output_lock(root):
                            self.fail("Concurrent writer acquired lock")
                    raise RuntimeError("test failure")
            with output_lock(root):
                pass
