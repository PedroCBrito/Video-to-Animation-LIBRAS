import copy
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from src.animation.rig_map import RigMapError, validate_rig_map, write_rig_map_report


MAP_PATH = Path(__file__).resolve().parents[1] / "config" / "rig-map.yaml"
REFERENCE_PATH = MAP_PATH.parent / "avatar-hands-reference.json"


def _write_altered_map(folder, mapping):
    altered = Path(folder) / "rig-map.yaml"
    altered.write_text(yaml.safe_dump(mapping), encoding="utf-8")
    (Path(folder) / REFERENCE_PATH.name).write_bytes(REFERENCE_PATH.read_bytes())
    return altered


def _avatar_report():
    mapping = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))
    target = mapping["target"]
    bones = []
    meshes = []
    for side, fingers in target["fingers"].items():
        groups = []
        for chain in fingers.values():
            for index, name in enumerate(chain):
                bones.append({"name": name, "parent": chain[index - 1] if index else None,
                              "head": [0.0 if side == "right" else 1.0, 0.0, 0.0]})
                groups.append(name)
        meshes.append({"name": target["meshes"][side], "armature_modifiers": ["Armature"],
                       "vertex_groups": groups})
    return {
        "avatar_sha256": target["avatar_sha256"],
        "inventory": {"candidate_rigs": ["Armature"],
                      "armatures": [{"name": "Armature", "bones": bones}], "meshes": meshes},
    }


class RigMapTests(unittest.TestCase):
    def test_target_map_covers_both_meshes_and_all_38_bones(self):
        result = validate_rig_map(MAP_PATH, _avatar_report())
        self.assertEqual(result.target_bone_count, 38)
        self.assertEqual(result.target_armature, "Armature")
        self.assertEqual(result.source_status, "pending_real_cp2_skeleton")
        self.assertEqual(result.calibration_status, "pending_real_cp2_skeleton")

    def test_wrong_avatar_or_swapped_hand_fails(self):
        report = _avatar_report()
        changed = copy.deepcopy(report)
        changed["avatar_sha256"] = "0" * 64
        with self.assertRaisesRegex(RigMapError, "outra versão"):
            validate_rig_map(MAP_PATH, changed)

        changed = copy.deepcopy(report)
        changed["inventory"]["meshes"][0]["vertex_groups"] = changed["inventory"]["meshes"][1]["vertex_groups"]
        with self.assertRaisesRegex(RigMapError, "trocada"):
            validate_rig_map(MAP_PATH, changed)

    def test_missing_bone_and_broken_chain_fail(self):
        report = _avatar_report()
        changed = copy.deepcopy(report)
        changed["inventory"]["armatures"][0]["bones"].pop()
        with self.assertRaisesRegex(RigMapError, "ausente"):
            validate_rig_map(MAP_PATH, changed)

        changed = copy.deepcopy(report)
        changed["inventory"]["armatures"][0]["bones"][1]["parent"] = None
        with self.assertRaisesRegex(RigMapError, "Hierarquia"):
            validate_rig_map(MAP_PATH, changed)

    def test_real_source_inventory_must_contain_mapped_bones(self):
        mapping = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))
        required = {name for side in mapping["source"]["fingers"].values()
                    for chain in side.values() for name in chain}
        required.update(mapping["source"]["hand_bones"].values())
        source = {"armatures": [{"bones": [{"name": name} for name in required]}]}
        self.assertEqual(validate_rig_map(MAP_PATH, _avatar_report(), source).source_status, "validated")
        source["armatures"][0]["bones"].pop()
        with self.assertRaisesRegex(RigMapError, "não contém"):
            validate_rig_map(MAP_PATH, _avatar_report(), source)

    def test_duplicate_bone_in_map_is_rejected(self):
        mapping = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))
        mapping["target"]["fingers"]["right"]["index"][0] = mapping["target"]["fingers"]["right"]["thumb"][0]
        with tempfile.TemporaryDirectory() as folder:
            altered = _write_altered_map(folder, mapping)
            with self.assertRaisesRegex(RigMapError, "repetido"):
                validate_rig_map(altered, _avatar_report())

    def test_rejects_swapped_target_sides_and_fingers(self):
        original = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))
        for mutation in ("sides", "fingers"):
            mapping = copy.deepcopy(original)
            if mutation == "sides":
                for field in ("meshes", "fingers"):
                    values = mapping["target"][field]
                    values["right"], values["left"] = values["left"], values["right"]
            else:
                values = mapping["target"]["fingers"]["right"]
                values["index"], values["middle"] = values["middle"], values["index"]
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(RigMapError, "referência anatômica"):
                    validate_rig_map(_write_altered_map(folder, mapping), _avatar_report())

    def test_rejects_invalid_calibration_and_backend(self):
        original = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))
        for field, value in (("rest_pose_alignment", "invalid"), ("hand_scale", "invalid")):
            mapping = copy.deepcopy(original)
            mapping["calibration"][field] = value
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(RigMapError, field):
                    validate_rig_map(_write_altered_map(folder, mapping), _avatar_report())
        mapping = copy.deepcopy(original)
        mapping["source"]["freemocap_version"] = "0.0"
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RigMapError, "FreeMoCap"):
                validate_rig_map(_write_altered_map(folder, mapping), _avatar_report())

    def test_persists_coverage_and_pending_gates(self):
        result = validate_rig_map(MAP_PATH, _avatar_report())
        with tempfile.TemporaryDirectory() as folder:
            path = write_rig_map_report(result, _avatar_report(), Path(folder))
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pending_cp2_calibration")
            self.assertEqual(set(report["coverage"]), {"right", "left"})
            self.assertEqual(len(report["coverage"]["right"]), 5)


if __name__ == "__main__":
    unittest.main()
