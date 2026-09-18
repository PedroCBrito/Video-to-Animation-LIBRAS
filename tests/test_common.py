"""Tests for shared infrastructure primitives."""

import hashlib
from pathlib import Path
import tempfile
import unittest

from src.common import sha256_file, write_json_atomic


class CommonTests(unittest.TestCase):
    def test_sha256_file_matches_standard_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.bin"
            path.write_bytes(b"common bytes")
            self.assertEqual(sha256_file(path), hashlib.sha256(b"common bytes").hexdigest())

    def test_atomic_json_write_creates_parent_and_utf8_document(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "nested" / "manifest.json"
            write_json_atomic(destination, {"message": "ação", "value": 1})
            self.assertEqual(destination.read_text(encoding="utf-8"), '{\n  "message": "ação",\n  "value": 1\n}\n')
            self.assertEqual(list(destination.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
