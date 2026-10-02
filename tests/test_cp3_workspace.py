import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.application import run_ingestion
from src.preparation.pipeline import _run_id
from src.preparation.profile import MediaPreparationProfile


class WorkspaceTests(unittest.TestCase):
    def test_capture_profile_changes_workspace_identity_but_not_legacy_stages(self):
        entry = {"clip_id": "clip-a", "sha256": "source-a"}
        profile = MediaPreparationProfile()
        legacy = _run_id(entry, profile, "ffmpeg")
        first = _run_id(dict(entry, processing_namespace="capture-1"), profile, "ffmpeg")
        second = _run_id(dict(entry, processing_namespace="capture-2"), profile, "ffmpeg")
        self.assertEqual(len({legacy, first, second}), 3)
        self.assertEqual(first, _run_id(dict(entry, processing_namespace="capture-1"), profile, "ffmpeg"))

    def test_internal_work_is_separate_and_output_previews_are_excluded_from_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input"
            source.mkdir()
            (source / "sign.mp4").write_bytes(b"source video")
            output = source / "results"
            generated = output / "review/previous/preview.mp4"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"generated preview")
            seen_outputs = []
            def noop(report, *args, **kwargs):
                seen_outputs.append(report["output"])
                return report
            def extractor(recording):
                pass
            extractor.profile_fingerprint = "capture-profile"
            with patch("src.application.ingestion_service.MediaInspector"), \
                    patch("src.application.ingestion_service.inspect_inventory", side_effect=noop), \
                    patch("src.application.ingestion_service.prepare_inventory", side_effect=noop), \
                    patch("src.application.ingestion_service.create_sessions", side_effect=noop), \
                    patch("src.application.ingestion_service.verify_inventory", side_effect=noop), \
                    patch("src.application.ingestion_service.extract_inventory", side_effect=noop), \
                    patch("src.animation.retarget_stage._verified_source", return_value=source / "sign.mp4"):
                result = run_ingestion(source, output, "retarget", extractor=extractor,
                                       retargeter=lambda *args: {"status": "review", "reason": "Inspection pending"})
            self.assertEqual(len(result.report["entries"]), 1)
            self.assertTrue(all(Path(p) == output / ".pipeline" for p in seen_outputs))
            self.assertEqual(result.report["entries"][0]["processing_namespace"], "capture-profile")
            self.assertTrue(result.report_path.is_relative_to(output / ".pipeline"))
            state = json.loads((output / ".pipeline/state.json").read_text())
            self.assertEqual(state["status"], "review")
            self.assertEqual(state["execution_status"], "completed")
            self.assertFalse((output / "state.json").exists())
