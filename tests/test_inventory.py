import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.ingestion.contracts import validate_paths
from src.ingestion.inventory import build_inventory, load_metadata, report_exit_code


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "vídeos com espaços"
        self.source.mkdir()
        self.paths = validate_paths(self.source, self.source / "saída", directory=True)

    def put(self, relative, content=b"fixture"):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_stable_ids_duplicate_names_output_exclusion_and_hashes(self):
        self.put("b/sinal.MP4")
        self.put("a/sinal.mp4")
        self.put("saída/generated.mp4")
        before = {p: p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        first = build_inventory(self.paths)
        second = build_inventory(self.paths)
        entries = first["entries"]
        self.assertEqual([e["relative_path"] for e in entries], ["a/sinal.mp4", "b/sinal.MP4"])
        self.assertNotEqual(entries[0]["clip_id"], entries[1]["clip_id"])
        self.assertEqual(entries, second["entries"])
        self.assertEqual(entries[0]["sha256"], hashlib.sha256(b"fixture").hexdigest())
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(report_exit_code(first), 0)

    def test_empty_unsupported_and_empty_directory_are_reported(self):
        self.assertEqual(report_exit_code(build_inventory(self.paths)), 2)
        self.put("empty.mp4", b"")
        self.put("notes.txt")
        result = build_inventory(self.paths)
        self.assertEqual(result["summary"]["by_status"], {"invalid": 1, "unsupported": 1})
        self.assertEqual(report_exit_code(result), 2)

    def test_metadata_is_explicit_preserved_and_unmatched_reported(self):
        self.put("sinal.mp4")
        metadata = self.source / "metadata.json"
        values = {"gloss": "OLÁ", "signer": "A", "custom": {"take": 2}}
        metadata.write_text(json.dumps({"schema_version": "1.0", "clips": {
            "sinal.mp4": values, "missing.mp4": {"id": 9},
        }}), encoding="utf-8")
        result = build_inventory(self.paths, metadata)
        by_name = {e["relative_path"]: e for e in result["entries"]}
        self.assertEqual(by_name["sinal.mp4"]["metadata"], values)
        self.assertEqual(by_name["metadata.json"]["status"], "skipped")
        self.assertEqual(result["unmatched_metadata"], ["missing.mp4"])
        self.assertEqual(report_exit_code(result), 2)

    def test_bad_metadata_paths_and_duplicate_keys_rejected(self):
        metadata = self.root / "metadata.json"
        for key in ("../escape.mp4", "/absolute.mp4", "a\\b.mp4", "a/./b.mp4"):
            metadata.write_text(json.dumps({"schema_version": "1.0", "clips": {key: {}}}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_metadata(metadata)
        metadata.write_text('{"schema_version":"1.0","clips":{"a":{},"a":{}}}')
        with self.assertRaises(ValueError):
            load_metadata(metadata)

    def test_unreadable_file_does_not_abort_others(self):
        self.put("a.mp4")
        self.put("b.mp4")
        with patch("src.ingestion.inventory.file_hash", side_effect=[PermissionError("denied"), "hash"]):
            result = build_inventory(self.paths)
        self.assertEqual([e["status"] for e in result["entries"]], ["invalid", "ready"])

    def test_single_file_same_identity_as_directory(self):
        video = self.put("video.mov")
        single = validate_paths(video, self.paths.output, directory=False)
        self.assertEqual(build_inventory(single)["entries"], build_inventory(self.paths)["entries"])

    def test_cli_inventory_runs_without_third_party_packages(self):
        self.put("video.mp4")
        result = subprocess.run([
            sys.executable, "-S", "cli.py", "--input-dir", str(self.source),
            "--output-dir", str(self.paths.output), "--until-stage", "inventory",
        ], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = list((self.paths.output / "reports").glob("*.json"))
        self.assertEqual(len(reports), 1)
        self.assertEqual(json.loads(reports[0].read_text(encoding="utf-8"))["stage"], "inventory")


if __name__ == "__main__":
    unittest.main()
