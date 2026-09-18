import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.ingestion.contracts import new_report, validate_paths, write_report


class IngestionFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "entrada com espaços"
        self.source.mkdir()

    def test_rejects_equal_or_parent_output_before_writing(self):
        for output in (self.source, self.root):
            with self.subTest(output=output), self.assertRaises(ValueError):
                validate_paths(self.source, output, directory=True)
        self.assertEqual(list(self.source.iterdir()), [])

    def test_nested_output_and_unicode_report(self):
        paths = validate_paths(self.source, self.source / "saída", directory=True)
        report = new_report("inventory", paths)
        report["note"] = "intérprete"
        destination = write_report(report, paths.output)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), report)
        before = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            write_report(report, paths.output)
        self.assertEqual(destination.read_bytes(), before)

    def test_failed_serialization_does_not_publish_partial_json(self):
        paths = validate_paths(self.source, self.root / "output", directory=True)
        report = new_report("inventory", paths)
        report["invalid"] = float("nan")
        with self.assertRaises(ValueError):
            write_report(report, paths.output)
        self.assertEqual(list((paths.output / "reports").iterdir()), [])

    def test_missing_input_or_wrong_kind(self):
        with self.assertRaises(FileNotFoundError):
            validate_paths(self.root / "missing", self.root / "out", directory=True)
        with self.assertRaises(ValueError):
            validate_paths(self.source, self.root / "out", directory=False)

    def test_cli_help_without_site_packages(self):
        # -S disables third-party packages, including PyYAML and FreeMoCap.
        result = subprocess.run(
            [sys.executable, "-S", "cli.py", "--help"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--video", result.stdout)


if __name__ == "__main__":
    unittest.main()
