import json
from pathlib import Path
import tempfile
import threading
import unittest

from src.application import IngestionCancelled, run_ingestion


class ApplicationServiceTests(unittest.TestCase):
    def test_inventory_service_emits_progress_and_persists_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "entrada"
            source.mkdir()
            (source / "sinal.mp4").write_bytes(b"video")
            output = root / "saida"
            events = []

            result = run_ingestion(source, output, "inventory", progress_callback=events.append)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual([event["progress_percent"] for event in events], [0, 100, 100])
            state = json.loads((output / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["progress_percent"], 100)
            self.assertTrue(result.report_path.is_file())

    def test_service_cancellation_is_recorded_without_publishing_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "entrada"
            source.mkdir()
            (source / "sinal.mp4").write_bytes(b"video")
            output = root / "saida"
            cancel_event = threading.Event()
            cancel_event.set()

            with self.assertRaises(IngestionCancelled):
                run_ingestion(source, output, "inventory", cancel_event=cancel_event)

            state = json.loads((output / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "cancelled")
            self.assertFalse((output / "reports").exists())
