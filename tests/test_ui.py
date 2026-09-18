from pathlib import Path
import tempfile
import unittest

from src.ui.app import STAGE_LABELS, progress_text, validate_selection


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
        self.assertEqual(set(STAGE_LABELS), {"inventory", "inspect", "prepare", "session", "verify"})
