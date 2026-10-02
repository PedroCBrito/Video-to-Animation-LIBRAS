import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.animation.retarget_stage import retarget_inventory, retarget_exit_code
from src.common import sha256_file


class RetargetStageTests(unittest.TestCase):
    def test_empty_inventory_is_not_a_successful_delivery(self):
        self.assertEqual(retarget_exit_code({"entries": [], "retarget_summary": {}}), 2)

    def _entry(self, root: Path):
        recording = root / "freemocap"
        recording.mkdir()
        blend = recording / "source_skeleton.blend"
        blend.write_bytes(b"BLENDER-test-source")
        extraction = {"status": "completed", "clip_id": "clip-a", "run_id": "run-a"}
        (recording / "freemocap.json").write_text(json.dumps(extraction), encoding="utf-8")
        (recording / "session.json").write_text(json.dumps({"status": "session_ready"}), encoding="utf-8")
        evidence = {"status": "pass", "extraction_manifest_sha256": sha256_file(recording / "freemocap.json")}
        (recording / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
        source = {
            "status": "completed", "clip_id": "clip-a", "run_id": "run-a",
            "output_path": blend.name, "output_sha256": sha256_file(blend),
            "extraction_manifest_sha256": sha256_file(recording / "freemocap.json"),
            "session_manifest_sha256": sha256_file(recording / "session.json"),
        }
        (recording / "source_skeleton.json").write_text(json.dumps(source), encoding="utf-8")
        return {
            "clip_id": "clip-a", "session": {"status": "session_ready", "run_id": "run-a",
                                       "recording_path": str(recording)},
            "extraction": {"status": "completed", "extraction": extraction, "source_skeleton": source, "evidence": evidence},
        }, blend

    def test_verified_cp2_output_reaches_callback_automatically(self):
        with tempfile.TemporaryDirectory() as folder:
            entry, blend = self._entry(Path(folder))
            received = []
            report = retarget_inventory({"entries": [entry]},
                                        lambda source, item: received.append((source, item["clip_id"]))
                                        or {"status": "completed"})
            self.assertEqual(received, [(blend.resolve(), "clip-a")])
            self.assertEqual(retarget_exit_code(report), 0)

    def test_changed_source_and_wrong_cp2_identity_prevent_callback(self):
        for mutation in ("tamper", "other_clip"):
            with tempfile.TemporaryDirectory() as folder:
                entry, blend = self._entry(Path(folder))
                if mutation == "tamper":
                    blend.write_bytes(b"BLENDER-corrupted")
                else:
                    entry["clip_id"] = "another-clip"
                calls = []
                report = retarget_inventory({"entries": [entry]},
                                            lambda source, item: calls.append(source) or {"status": "completed"})
                self.assertEqual(calls, [])
                self.assertEqual(report["retarget_summary"], {"failed": 1})
                self.assertEqual(retarget_exit_code(report), 2)

    def test_reviewed_cp2_is_not_published(self):
        with tempfile.TemporaryDirectory() as folder:
            entry, _ = self._entry(Path(folder))
            entry["extraction"]["status"] = "review"
            report = retarget_inventory({"entries": [entry]},
                                        lambda source, item: self.fail("must not retarget"))
            self.assertEqual(report["retarget_summary"], {"not_run": 1})
