from pathlib import Path
import sys
import tempfile
import threading
import unittest

from src.integrations.freemocap import FreeMoCapAdapter, FreeMoCapAdapterError
from src.integrations.process import run_process


class FreeMoCapAdapterTests(unittest.TestCase):
    def test_adapter_builds_argv_without_shell_interpretation(self):
        adapter = FreeMoCapAdapter(
            python_executable=sys.executable,
            command_template=(sys.executable, "-c", "print('ok')", "{session_dir}", "{config_path}"),
        )
        command = adapter.build_command(Path("folder with spaces"), Path("profile;unsafe.json"))
        self.assertEqual(command[3], str(Path("folder with spaces").resolve()))
        self.assertEqual(command[4], str(Path("profile;unsafe.json").resolve()))
        self.assertFalse(any("shell=True" in value for value in command))

    def test_adapter_captures_success_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder) / "session"
            session.mkdir()
            success = FreeMoCapAdapter(
                python_executable=sys.executable,
                command_template=(sys.executable, "-c", "print('backend ok')", "{session_dir}"),
            ).process_session(session, timeout=10)
            failure = FreeMoCapAdapter(
                python_executable=sys.executable,
                command_template=(sys.executable, "-c", "import sys; print('backend failed', file=sys.stderr); sys.exit(3)", "{session_dir}"),
            ).process_session(session, timeout=10)
        self.assertTrue(success.succeeded)
        self.assertIn("backend ok", success.stdout)
        self.assertFalse(failure.succeeded)
        self.assertEqual(failure.returncode, 3)
        self.assertIn("backend failed", failure.stderr)

    def test_process_timeout_and_cancellation_are_explicit(self):
        timeout = run_process(
            (sys.executable, "-c", "import time; time.sleep(2)"),
            cwd=Path.cwd(), timeout=0.1,
        )
        cancel_event = threading.Event()
        cancel_event.set()
        cancelled = run_process(
            (sys.executable, "-c", "import time; time.sleep(2)"),
            cwd=Path.cwd(), timeout=10, cancel_event=cancel_event,
        )
        self.assertTrue(timeout.timed_out)
        self.assertFalse(timeout.succeeded)
        self.assertTrue(cancelled.cancelled)

    def test_invalid_adapter_contract_is_rejected(self):
        with self.assertRaises(FreeMoCapAdapterError):
            FreeMoCapAdapter()
        with self.assertRaises(FreeMoCapAdapterError):
            FreeMoCapAdapter(entrypoint="invalid-entrypoint")
