from pathlib import Path
import tempfile
import unittest

from src.extraction.profile import ExtractionProfileError, load_extraction_profile, resolve_extraction_profile


SUPPORTED = {
    "model_complexity": {"type": "integer", "minimum": 0, "maximum": 2, "default": 1},
    "enable_filter": {"type": "boolean", "default": False},
    "cutoff_hz": {"type": "number", "minimum": 0.1, "maximum": 20.0, "required": True},
    "depth_mode": {"type": "string", "choices": ["monocular", "disabled"], "default": "monocular"},
}


class ExtractionProfileTests(unittest.TestCase):
    def test_profile_maps_defaults_and_generates_deterministic_fingerprint(self):
        data = {
            "schema_version": "1.0",
            "name": "reference",
            "backend": {"name": "freemocap", "version": "1.8.2", "entrypoint": "fake:process"},
            "parameters": {"model": 2, "filter": True, "cutoff": 5.0},
            "parameter_map": {"model": "model_complexity", "filter": "enable_filter", "cutoff": "cutoff_hz"},
            "metadata": {"fps_policy": "preserve", "depth_source": "monocular"},
        }
        profile = resolve_extraction_profile(data, {
            **SUPPORTED,
        })
        repeated = resolve_extraction_profile(data, SUPPORTED)
        self.assertEqual(profile.fingerprint, repeated.fingerprint)
        self.assertEqual(profile.applied_parameters["model_complexity"], 2)
        self.assertEqual(profile.applied_parameters["depth_mode"], "monocular")
        self.assertEqual(profile.defaults_applied["depth_mode"], "monocular")

    def test_profile_rejects_unknown_type_range_and_duplicate_mapping(self):
        base = {"name": "invalid", "parameters": {"value": 1}}
        with self.assertRaisesRegex(ExtractionProfileError, "unsupported"):
            resolve_extraction_profile(base, SUPPORTED)
        with self.assertRaisesRegex(ExtractionProfileError, "above"):
            resolve_extraction_profile({"name": "invalid", "parameters": {"value": 21},
                                        "parameter_map": {"value": "cutoff_hz"}}, SUPPORTED)
        with self.assertRaisesRegex(ExtractionProfileError, "Multiple"):
            resolve_extraction_profile({"name": "invalid", "parameters": {"a": 1, "b": True},
                                        "parameter_map": {"a": "model_complexity", "b": "model_complexity"}}, SUPPORTED)

    def test_profile_rejects_missing_required_and_invalid_enum(self):
        with self.assertRaisesRegex(ExtractionProfileError, "Required"):
            resolve_extraction_profile({"name": "missing", "parameters": {}}, SUPPORTED)
        with self.assertRaisesRegex(ExtractionProfileError, "one of"):
            resolve_extraction_profile({"name": "bad", "parameters": {
                "depth_mode": "stereo", "cutoff_hz": 5.0,
            }}, SUPPORTED)

    def test_yaml_profile_is_loaded_and_resolved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.yaml"
            path.write_text(
                "name: yaml-profile\nbackend:\n  entrypoint: fake:process\nparameters:\n  cutoff_hz: 4.5\n",
                encoding="utf-8",
            )
            profile = load_extraction_profile(path, SUPPORTED)
        self.assertEqual(profile.name, "yaml-profile")
        self.assertEqual(profile.applied_parameters["cutoff_hz"], 4.5)
