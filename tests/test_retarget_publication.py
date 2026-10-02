"""Publication gates must never turn a reviewed/cancelled artifact into approval."""
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import patch

from src.animation.retargeting import publish_animation, publish_review
from src.common import sha256_file
from src.ui.app import IngestionApp


class PublicationTests(unittest.TestCase):
    def fixture(self, root):
        work = root / "work"
        work.mkdir()
        (work / "animation.blend").write_bytes(b"baked-test")
        (work / "preview.mp4").write_bytes(b"compact preview")
        digest = sha256_file(work / "animation.blend")
        return work, {"status": "completed", "clip_id": "clip-a", "run_id": "run-a",
                      "video_sha256": "video", "animation_sha256": digest,
                      "preview_sha256": sha256_file(work / "preview.mp4"),
                      "frame_start": 0, "frame_end": 1,
                      "visual_review": {"status": "pass", "animation_sha256": digest, "video_sha256": "video",
                                        "reviewer": "test", "notes": "Controlled fixture",
                                        "intervals": [{"hand": s, "start": 0, "end": 1, "notes": "Checked"}
                                                      for s in ("right", "left")]},
                      "reopen_check": {"status": "pass"}}

    def test_atomic_bundle_has_matching_metadata_and_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work, metadata = self.fixture(root)
            result = publish_animation(work, root, metadata)
            self.assertEqual(sha256_file(result / "animation.blend"), metadata["animation_sha256"])
            self.assertTrue((result / "preview.mp4").is_file())
            self.assertEqual({p.name for p in result.iterdir()}, {"animation.blend", "preview.mp4", "metadata.json"})
            self.assertEqual(json.loads((result / "metadata.json").read_text()), metadata)
            self.assertEqual(list(result.parent.glob(".publishing-*")), [])

    def test_review_is_accessible_and_promoted_without_duplicate_user_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work, metadata = self.fixture(root)
            metadata["status"] = "review"
            metadata["visual_review"]["status"] = "review"
            review = publish_review(work, root, metadata)
            self.assertIsNone(publish_animation(work, root, metadata))
            self.assertEqual(publish_review(work, root, metadata), review)
            metadata["status"] = "completed"
            metadata["visual_review"]["status"] = "pass"
            delivered = publish_animation(work, root, metadata)
            self.assertFalse(review.exists())
            self.assertTrue(delivered.is_dir())

    def test_review_failure_cancellation_and_stale_approval_do_not_publish(self):
        for case in ("review", "failed", "cancelled", "stale", "changed", "reopen"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                work, metadata = self.fixture(root)
                cancel = threading.Event()
                if case in {"review", "failed"}:
                    metadata["status"] = case
                    self.assertIsNone(publish_animation(work, root, metadata))
                else:
                    if case == "cancelled":
                        cancel.set()
                    elif case == "stale":
                        metadata["visual_review"]["animation_sha256"] = "different"
                    elif case == "changed":
                        (work / "animation.blend").write_bytes(b"changed")
                    else:
                        metadata["reopen_check"]["status"] = "fail"
                    with self.assertRaises((ValueError, RuntimeError, InterruptedError)):
                        publish_animation(work, root, metadata, cancel_event=cancel)
                self.assertFalse((root / "animations").exists())

    def test_gui_worker_uses_shared_backend_and_complete_service(self):
        app = object.__new__(IngestionApp)
        app._events = queue.Queue()
        app.avatar_path = Path("animation.blend")
        app.rig_map_path = Path("config/rig-map-depth.yaml")
        cancel = threading.Event()
        with patch("src.application.backends.build_extractor", return_value="extract") as extract, \
                patch("src.application.backends.build_retargeter", return_value="retarget") as retarget, \
                patch("src.ui.app.run_ingestion", return_value="result") as service:
            app._run_worker(Path("video.mp4"), Path("output"), cancel,
                            {"blender": "blender.exe", "ffprobe": "ffprobe", "ffmpeg": "ffmpeg"})
        self.assertEqual(service.call_args.args[2], "retarget")
        self.assertEqual(service.call_args.kwargs["extractor"], "extract")
        self.assertEqual(service.call_args.kwargs["retargeter"], "retarget")
        self.assertIs(extract.call_args.kwargs["cancel_event"], cancel)
        self.assertIs(retarget.call_args.kwargs["cancel_event"], cancel)
        self.assertEqual(app._events.get_nowait(), ("success", "result"))
