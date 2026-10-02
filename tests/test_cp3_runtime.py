import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.integrations.process import run_process
from src.integrations.runtime import backend_environment
from src.integrations.freemocap_worker import main


class RuntimeTests(unittest.TestCase):
    def test_timeout_stops_descendants_that_could_keep_writing_output(self):
        import time
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            child = root / "child.py"
            child.write_text("import time\nfrom pathlib import Path\ntime.sleep(1.5)\nPath('orphan-output.txt').write_text('unexpected')\n")
            parent = root / "parent.py"
            parent.write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'child.py'])\ntime.sleep(10)\n")
            result = run_process([sys.executable, str(parent)], cwd=root, timeout=0.4)
            self.assertTrue(result.timed_out)
            time.sleep(1.6)
            self.assertFalse((root / "orphan-output.txt").exists())

    def test_child_has_local_cache_and_utf8_without_mutating_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before = dict(os.environ)
            result = run_process(
                [sys.executable, "-c", "import os,json,sys,tempfile; print(json.dumps([os.environ['USERPROFILE'], 'ação', sys.pycache_prefix, tempfile.gettempdir()]))"],
                cwd=root, timeout=10, env=backend_environment(root / "runtime"),
            )
            self.assertTrue(result.succeeded, result.stderr)
            self.assertEqual(json.loads(result.stdout), [str((root / "runtime").resolve()), "ação",
                             str((root / "runtime/python-cache").resolve()), str((root / "runtime/temp").resolve())])
            self.assertEqual(dict(os.environ), before)

    def test_wrong_installed_backend_is_rejected_before_processing(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "profile.json"
            config.write_text(json.dumps({"backend": {"name": "freemocap", "version": "1.8.2"},
                                          "applied_parameters": {}}))
            with patch("src.integrations.freemocap_worker.importlib.metadata.version", return_value="2.0.0"), \
                    patch("src.integrations.freemocap_worker.invoke_entrypoint") as invoke:
                with self.assertRaisesRegex(RuntimeError, "perfil exige"):
                    main(["--session", folder, "--config", str(config), "--entrypoint", "module:fn",
                          "--session-argument", "recording_path"])
                invoke.assert_not_called()
