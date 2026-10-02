from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from src.integrations.freemocap import FreeMoCapAdapter, FreeMoCapAdapterError
from src.integrations.process import run_process
from src.integrations.freemocap_worker import invoke_entrypoint


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

    def test_verbose_backend_does_not_block_on_full_stdout_or_stderr_pipe(self):
        result = run_process(
            (sys.executable, "-c",
             "import sys; sys.stdout.write('x'*200000); sys.stdout.flush(); "
             "sys.stderr.write('y'*200000); sys.stderr.flush()"),
            cwd=Path.cwd(), timeout=10,
        )
        self.assertTrue(result.succeeded)
        self.assertEqual(len(result.stdout), 200000)
        self.assertEqual(len(result.stderr), 200000)

    def test_invalid_adapter_contract_is_rejected(self):
        with self.assertRaises(FreeMoCapAdapterError):
            FreeMoCapAdapter()
        with self.assertRaises(FreeMoCapAdapterError):
            FreeMoCapAdapter(entrypoint="invalid-entrypoint")

    def test_worker_rejects_options_not_accepted_by_real_entrypoint_signature(self):
        def backend(recording_path, run_blender=False):
            return recording_path, run_blender

        with patch("src.integrations.freemocap_worker._load_entrypoint", return_value=backend):
            self.assertEqual(
                invoke_entrypoint("example:backend", Path("session"), "recording_path", {"run_blender": False})[1],
                False,
            )
            with self.assertRaisesRegex(RuntimeError, "not accept options: unknown"):
                invoke_entrypoint("example:backend", Path("session"), "recording_path", {"unknown": 1})

    def test_worker_unwraps_effective_profile_before_calling_backend(self):
        import json
        from src.integrations.freemocap_worker import main
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "effective.json"
            config.write_text(json.dumps({"schema_version": "1.0", "applied_parameters": {"run_blender": False}}))
            with patch("src.integrations.freemocap_worker.invoke_entrypoint") as invoke:
                self.assertEqual(main(["--session", folder, "--entrypoint", "module:function",
                                       "--session-argument", "recording_path", "--config", str(config)]), 0)
            self.assertEqual(invoke.call_args.args[-1], {"run_blender": False})
