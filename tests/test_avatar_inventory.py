import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import patch

from cli import main as cli_main
from src.animation.avatar_inventory import AvatarInventoryError, AvatarInventoryResult, inspect_avatar
from src.animation.rig_map import RigMapResult
from src.integrations.process import ProcessResult
from src.ui.app import IngestionApp


def _inventory(*, rigs=1):
    armatures = [{
        "name": f"Rig-{index}", "bones": [{"name": "Bone"}], "linked_meshes": [f"Mesh-{index}"],
    } for index in range(rigs)]
    return {
        "schema_version": "1.0", "blender_version": "5.2.2", "armatures": armatures,
        "candidate_rigs": [item["name"] for item in armatures], "actions": [],
    }


class AvatarInventoryTests(unittest.TestCase):
    def _files(self, root):
        avatar = root / "character.blend"
        avatar.write_bytes(b"BLENDER-v405")
        blender = root / "blender.exe"
        blender.write_bytes(b"test executable")
        return avatar, blender

    def test_publishes_verified_inventory_without_touching_avatar(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            avatar, blender = self._files(root)
            before = avatar.read_bytes()
            commands = []

            def runner(command, **kwargs):
                commands.append(command)
                Path(command[-1]).write_text(json.dumps(_inventory()), encoding="utf-8")
                return ProcessResult(tuple(command), 0, "ok", "", 0.2)

            result = inspect_avatar(avatar, blender, root / "output", process_runner=runner)
            self.assertEqual(result.report["rig_status"], "identified")
            self.assertEqual(result.report["candidate_rig"], "Rig-0")
            self.assertEqual(result.report["semantic_coverage"], "pending_review")
            self.assertEqual(json.loads(result.report_path.read_text(encoding="utf-8")), result.report)
            self.assertEqual(avatar.read_bytes(), before)
            self.assertEqual(commands[0][1:3], ("--background", "--factory-startup"))
            self.assertEqual(commands[0][-2], str(avatar.resolve()))

    def test_rejects_invalid_blend_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            avatar, blender = self._files(root)
            avatar.write_bytes(b"not a blend")
            with self.assertRaisesRegex(AvatarInventoryError, "não é um .blend válido"):
                inspect_avatar(avatar, blender, root / "output", process_runner=lambda *a, **k: None)
            self.assertFalse((root / "output").exists())

    def test_rejects_incomplete_or_failed_blender_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            avatar, blender = self._files(root)

            def invalid_runner(command, **kwargs):
                Path(command[-1]).write_text('{"schema_version":"1.0"}', encoding="utf-8")
                return ProcessResult(tuple(command), 0, "", "", 0.2)

            with self.assertRaises(AvatarInventoryError):
                inspect_avatar(avatar, blender, root / "output", process_runner=invalid_runner)
            self.assertEqual(list((root / "output" / "reports").glob("avatar-*.json")), [])

            def failed_runner(command, **kwargs):
                return ProcessResult(tuple(command), 1, "", "Blender failed", 0.2)

            with self.assertRaisesRegex(AvatarInventoryError, "Blender failed"):
                inspect_avatar(avatar, blender, root / "output", process_runner=failed_runner)

    def test_multiple_rigs_are_reported_as_ambiguous(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            avatar, blender = self._files(root)

            def runner(command, **kwargs):
                Path(command[-1]).write_text(json.dumps(_inventory(rigs=2)), encoding="utf-8")
                return ProcessResult(tuple(command), 0, "", "", 0.2)

            result = inspect_avatar(avatar, blender, root / "output", process_runner=runner)
            self.assertEqual(result.report["rig_status"], "ambiguous")
            self.assertIsNone(result.report["candidate_rig"])

    def test_cli_and_gui_call_shared_inspector(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            avatar, blender = self._files(root)
            report = AvatarInventoryResult(
                {"rig_status": "identified", "candidate_rig": "Rig-0"}, root / "report.json",
            )
            with patch("src.animation.inspect_avatar", return_value=report) as cli_inspect:
                code = cli_main(["--inspect-avatar", str(avatar), "--blender", str(blender),
                                 "--output-dir", str(root / "output")])
            self.assertEqual(code, 0)
            cli_inspect.assert_called_once_with(avatar, blender, root / "output/.pipeline")

            app = object.__new__(IngestionApp)
            app._events = queue.Queue()
            app.rig_map_path = root / "missing-rig-map.yaml"
            with patch("src.ui.app.inspect_avatar", return_value=report) as gui_inspect:
                app._inspect_avatar_worker(avatar, blender, root / "output", threading.Event())
            gui_inspect.assert_called_once()
            self.assertEqual(app._events.get_nowait(), ("avatar_inventory", (report, None)))

    def test_gui_worker_validates_configured_rig_map(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            avatar, blender = self._files(root)
            map_path = root / "rig-map.yaml"
            map_path.write_text("schema_version: '1.0'", encoding="utf-8")
            inventory = AvatarInventoryResult({"candidate_rig": "Armature"}, root / "avatar.json")
            mapped = RigMapResult("hash", "Armature", 38, "pending_real_cp2_skeleton",
                                  "pending_real_cp2_skeleton", {})
            app = object.__new__(IngestionApp)
            app._events = queue.Queue()
            app.rig_map_path = map_path
            with patch("src.ui.app.inspect_avatar", return_value=inventory), \
                    patch("src.ui.app.validate_rig_map", return_value=mapped) as validator, \
                    patch("src.ui.app.write_rig_map_report") as writer:
                app._inspect_avatar_worker(avatar, blender, root / "output", threading.Event())
            validator.assert_called_once_with(map_path, inventory.report)
            writer.assert_called_once_with(mapped, inventory.report, root / "output")
            self.assertEqual(app._events.get_nowait(), ("avatar_inventory", (inventory, mapped)))


if __name__ == "__main__":
    unittest.main()
