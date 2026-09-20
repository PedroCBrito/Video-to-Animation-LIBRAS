from pathlib import Path
import tempfile
import unittest

from src.ui.app import STAGE_LABELS, progress_text, validate_selection
from src.ui.dependencies import check_dependencies, missing_dependencies


class UiContractTests(unittest.TestCase):
    def test_validate_selection_accepts_file_and_output_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "sinal.mp4"
            source.write_bytes(b"video")
            paths = validate_selection(str(source), str(root / "saida"))
            self.assertFalse(paths.is_directory)
            self.assertEqual(paths.source, source.resolve())

    def test_progress_text_uses_human_readable_stage(self):
        message = progress_text({
            "stage": "prepare", "message": "Preparando.", "entries": 2,
            "current_entry": "sinal.mp4",
        })
        self.assertEqual(message, "Preparação dos vídeos: Preparando. (2 vídeo(s)) Vídeo atual: sinal.mp4.")
        self.assertEqual(set(STAGE_LABELS), {"inventory", "inspect", "prepare", "session", "verify", "extract"})

    def test_progress_text_exposes_entry_status_and_reason(self):
        message = progress_text({
            "stage": "inspect", "message": "Vídeo processado.",
            "current_entry": "sinal.mp4", "entry_status": "invalid",
            "entry_reason": "Arquivo truncado",
        })
        self.assertIn("Resultado: invalid.", message)
        self.assertIn("Motivo: Arquivo truncado.", message)

    def test_dependency_check_reports_tools_and_python_package(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ffmpeg = root / "ffmpeg.exe"
            ffprobe = root / "ffprobe.exe"
            blender = root / "blender.exe"
            for executable in (ffmpeg, ffprobe, blender):
                executable.write_bytes(b"test")

            paths = {"ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe), "blender": str(blender)}

            def fake_which(name):
                return paths.get(name)

            statuses = check_dependencies(
                environment={},
                which=fake_which,
                module_finder=lambda name: object() if name == "freemocap" else None,
            )

        self.assertEqual(missing_dependencies(statuses), [])
        self.assertTrue(all(status.available for status in statuses))

    def test_dependency_check_explains_missing_items(self):
        statuses = check_dependencies(
            environment={},
            which=lambda name: None,
            module_finder=lambda name: None,
            blender_discoverer=lambda: None,
        )
        missing = missing_dependencies(statuses)
        self.assertEqual({status.key for status in missing}, {"ffmpeg", "ffprobe", "freemocap", "blender"})
        self.assertTrue(all(status.detail for status in missing))

    def test_dependency_check_accepts_blender_found_on_another_drive(self):
        with tempfile.TemporaryDirectory() as folder:
            blender = Path(folder) / "D" / "Apps" / "Blender" / "blender.exe"
            blender.parent.mkdir(parents=True)
            blender.write_bytes(b"test")
            statuses = check_dependencies(
                environment={},
                which=lambda name: None,
                module_finder=lambda name: object() if name == "freemocap" else None,
                blender_discoverer=lambda: str(blender),
            )
        blender_status = next(status for status in statuses if status.key == "blender")
        self.assertTrue(blender_status.available)
        self.assertEqual(blender_status.location, str(blender.resolve()))
