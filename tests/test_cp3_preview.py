import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

from src.animation.preview import encode_preview
from src.common import write_json_atomic

FFMPEG = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")


class PreviewTests(unittest.TestCase):
    def test_sparse_frames_are_rejected_before_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json_atomic(root / "frames.json", {"frames": [0, 2], "fps": 30})
            with self.assertRaisesRegex(ValueError, "sequência completa"):
                encode_preview(root, "missing-tool")

    @unittest.skipUnless(FFMPEG and FFPROBE, "Configure media tools for the real preview test")
    def test_real_compact_preview_has_all_frames_and_no_temporary_output(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            preview = root / "frames"
            preview.mkdir()
            write_json_atomic(preview / "frames.json", {"frames": [0, 1, 2], "fps": 30000 / 1001})
            for frame in range(3):
                cv2.imwrite(str(preview / f"video-{frame:04d}.jpg"), np.full((180, 320, 3), frame * 90, dtype=np.uint8))
                cv2.imwrite(str(preview / f"avatar-{frame:04d}.png"), np.full((640, 640, 3), frame * 90, dtype=np.uint8))
            destination = encode_preview(preview, FFMPEG)
            checked = subprocess.run([FFPROBE, "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(destination)],
                                     capture_output=True, encoding="utf-8", timeout=30)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            stream = json.loads(checked.stdout)["streams"][0]
            self.assertEqual(int(stream["nb_read_frames"]), 3)
            self.assertEqual((stream["width"], stream["height"]), (1280, 640))
            self.assertFalse((root / ".preview.tmp.mp4").exists())
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(InterruptedError):
                encode_preview(preview, FFMPEG, cancel_event=cancel)
            self.assertTrue(destination.is_file())
