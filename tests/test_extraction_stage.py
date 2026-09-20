from pathlib import Path
import tempfile
import unittest

from src.extraction.stage import extract_inventory, extraction_exit_code


class ExtractionStageTests(unittest.TestCase):
    def test_extracts_only_ready_sessions_and_keeps_per_entry_status(self):
        report = {"entries": [
            {"relative_path": "ok.mp4", "session": {"status": "session_ready", "recording_path": "ok"}},
            {"relative_path": "bad.mp4", "session": {"status": "failed"}},
        ]}
        calls: list[Path] = []
        events = []

        def extractor(recording: Path):
            calls.append(recording)
            return {"status": "completed", "run_id": "run-1"}

        result = extract_inventory(report, extractor, lambda index, total, entry: events.append((index, total, entry)))

        self.assertEqual(len(calls), 1)
        self.assertEqual(result["entries"][0]["extraction"]["status"], "completed")
        self.assertEqual(result["entries"][1]["extraction"]["status"], "not_run")
        self.assertEqual(result["extraction_summary"], {"completed": 1, "not_run": 1})
        self.assertEqual(len(events), 2)
        self.assertEqual(extraction_exit_code(result), 2)

    def test_callback_failure_is_reported_without_aborting_other_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            recording = Path(folder) / "session"
            report = {"entries": [{
                "relative_path": "clip.mp4",
                "session": {"status": "session_ready", "recording_path": str(recording)},
            }]}

            result = extract_inventory(report, lambda path: (_ for _ in ()).throw(RuntimeError("backend unavailable")))

        self.assertEqual(result["entries"][0]["extraction"]["status"], "failed")
        self.assertIn("backend unavailable", result["entries"][0]["extraction"]["reason"])
        self.assertEqual(extraction_exit_code(result), 2)


if __name__ == "__main__":
    unittest.main()
