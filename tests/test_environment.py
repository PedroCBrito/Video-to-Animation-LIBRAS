import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.common import sha256_file
from src.integrations.environment import (
    check_python_package,
    check_tool,
    collect_environment_contract,
    write_environment_contract,
)


class EnvironmentContractTests(unittest.TestCase):
    def test_check_tool_captures_version_and_missing_executable(self):
        result = check_tool("python", sys.executable, "not-used")
        self.assertTrue(result.available)
        self.assertTrue(result.version)
        missing = check_tool("missing", "missing-executable-for-cp20", "missing-executable-for-cp20")
        self.assertFalse(missing.available)
        self.assertIn("não encontrado", missing.error.lower())

    def test_check_python_package_does_not_import_runtime(self):
        spec = type("Spec", (), {"origin": "/tmp/freemocap/__init__.py"})()
        result = check_python_package(
            module_finder=lambda name: spec,
            version_reader=lambda name: "1.8.2",
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["version"], "1.8.2")
        missing = check_python_package(module_finder=lambda name: None)
        self.assertFalse(missing["available"])

    def test_contract_validates_reference_session_and_publishes_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recording = root / "recording"
            videos = recording / "synchronized_videos"
            videos.mkdir(parents=True)
            video = videos / "camera_01.mp4"
            video.write_bytes(b"prepared video")
            prepared_hash = sha256_file(video)
            (recording / "session.json").write_text(json.dumps({
                "prepared_sha256": prepared_hash,
                "layout_contract": "freemocap_recording_v1",
            }), encoding="utf-8")
            contract = collect_environment_contract(
                reference_session=recording,
                ffmpeg=sys.executable,
                ffprobe=sys.executable,
                blender=sys.executable,
                backend_entrypoint="freemocap.fake:process",
                module_finder=lambda name: object(),
                version_reader=lambda name: "1.8.2",
            )
            destination = write_environment_contract(root / "environment.json", contract)
            saved = json.loads(destination.read_text(encoding="utf-8"))

        self.assertEqual(contract.status, "ready")
        self.assertTrue(contract.reference_session["valid"])
        self.assertEqual(saved["status"], "ready")
        self.assertEqual(saved["tools"]["ffmpeg"]["path"], str(Path(sys.executable).resolve()))

    def test_incomplete_contract_explains_missing_requirements(self):
        contract = collect_environment_contract(
            ffmpeg="missing-ffmpeg-cp20", ffprobe="missing-ffprobe-cp20",
            blender="missing-blender-cp20", module_finder=lambda name: None,
        )
        self.assertEqual(contract.status, "incomplete")
        self.assertFalse(contract.reference_session["valid"])
        self.assertFalse(contract.freemocap["available"])
        self.assertTrue(contract.tools["ffmpeg"].error)
