"""Versioned FreeMoCap profile mapping and validation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


class ExtractionProfileError(ValueError):
    """Raised when an extraction profile cannot be mapped safely."""


@dataclass(frozen=True)
class ExtractionProfile:
    """Requested and effective backend parameters for one extraction run."""

    schema_version: str
    name: str
    backend_name: str
    backend_version: str | None
    entrypoint: str | None
    requested_parameters: dict[str, Any]
    applied_parameters: dict[str, Any]
    defaults_applied: dict[str, Any]
    parameter_map: dict[str, str]
    metadata: dict[str, Any]
    fingerprint: str

    def as_dict(self, *, include_fingerprint: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "name": self.name,
            "backend": {
                "name": self.backend_name,
                "version": self.backend_version,
                "entrypoint": self.entrypoint,
            },
            "requested_parameters": self.requested_parameters,
            "applied_parameters": self.applied_parameters,
            "defaults_applied": self.defaults_applied,
            "parameter_map": self.parameter_map,
            "metadata": self.metadata,
        }
        if include_fingerprint:
            result["fingerprint"] = self.fingerprint
        return result


def _canonical(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _validate_value(name: str, value: Any, specification: Mapping[str, Any]) -> None:
    value_type = specification.get("type", "string")
    if value_type == "boolean":
        valid = isinstance(value, bool)
    elif value_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    elif value_type == "string":
        valid = isinstance(value, str)
    else:
        raise ExtractionProfileError(f"Unsupported type for parameter '{name}': {value_type}")
    if not valid:
        raise ExtractionProfileError(f"Parameter '{name}' must have type '{value_type}'.")
    if "minimum" in specification and value < specification["minimum"]:
        raise ExtractionProfileError(f"Parameter '{name}' is below the minimum value.")
    if "maximum" in specification and value > specification["maximum"]:
        raise ExtractionProfileError(f"Parameter '{name}' is above the maximum value.")
    choices = specification.get("choices")
    if choices is not None and value not in choices:
        raise ExtractionProfileError(f"Parameter '{name}' must be one of: {', '.join(map(str, choices))}.")


def resolve_extraction_profile(
    data: Mapping[str, Any],
    supported_parameters: Mapping[str, Mapping[str, Any]],
) -> ExtractionProfile:
    """Map project parameter names to the confirmed backend contract."""
    if not isinstance(data, Mapping):
        raise ExtractionProfileError("Extraction profile must be an object.")
    schema_version = str(data.get("schema_version", "1.0"))
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ExtractionProfileError("Extraction profile name is required.")
    backend = data.get("backend", {})
    if not isinstance(backend, Mapping):
        raise ExtractionProfileError("Profile backend must be an object.")
    backend_name = backend.get("name", "freemocap")
    if not isinstance(backend_name, str) or not backend_name.strip():
        raise ExtractionProfileError("Backend name is required.")
    backend_version = backend.get("version")
    if backend_version is not None and not isinstance(backend_version, str):
        raise ExtractionProfileError("Backend version must be a string.")
    entrypoint = backend.get("entrypoint")
    if entrypoint is not None and (not isinstance(entrypoint, str) or ":" not in entrypoint):
        raise ExtractionProfileError("Backend entrypoint must use the module:function format.")
    requested = data.get("parameters", data.get("options", {}))
    if not isinstance(requested, Mapping):
        raise ExtractionProfileError("Profile parameters must be an object.")
    parameter_map_data = data.get("parameter_map", {})
    if not isinstance(parameter_map_data, Mapping):
        raise ExtractionProfileError("Profile parameter_map must be an object.")
    parameter_map: dict[str, str] = {}
    for project_name in requested:
        target_name = parameter_map_data.get(project_name, project_name)
        if not isinstance(target_name, str) or not target_name:
            raise ExtractionProfileError(f"Invalid backend mapping for '{project_name}'.")
        if target_name in parameter_map.values():
            raise ExtractionProfileError(f"Multiple project parameters map to '{target_name}'.")
        parameter_map[str(project_name)] = target_name
        if target_name not in supported_parameters:
            raise ExtractionProfileError(
                f"Parameter '{project_name}' maps to unsupported backend option '{target_name}'."
            )

    applied: dict[str, Any] = {}
    defaults: dict[str, Any] = {}
    for backend_name_key, specification in supported_parameters.items():
        if not isinstance(specification, Mapping):
            raise ExtractionProfileError(f"Specification for '{backend_name_key}' must be an object.")
        if "default" in specification:
            default = specification["default"]
            _validate_value(backend_name_key, default, specification)
            applied[backend_name_key] = default
            defaults[backend_name_key] = default
        elif specification.get("required") and backend_name_key not in parameter_map.values():
            raise ExtractionProfileError(f"Required backend option '{backend_name_key}' is missing.")

    for project_name, value in requested.items():
        target_name = parameter_map[str(project_name)]
        specification = supported_parameters[target_name]
        _validate_value(target_name, value, specification)
        applied[target_name] = value
        defaults.pop(target_name, None)

    metadata = data.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ExtractionProfileError("Profile metadata must be an object.")
    metadata_dict = dict(metadata)
    unsigned = {
        "schema_version": schema_version,
        "name": name,
        "backend": {"name": backend_name, "version": backend_version, "entrypoint": entrypoint},
        "requested_parameters": dict(requested),
        "applied_parameters": applied,
        "defaults_applied": defaults,
        "parameter_map": parameter_map,
        "metadata": metadata_dict,
    }
    fingerprint = hashlib.sha256(_canonical(unsigned).encode("utf-8")).hexdigest()
    return ExtractionProfile(
        schema_version=schema_version,
        name=name,
        backend_name=backend_name,
        backend_version=backend_version,
        entrypoint=entrypoint,
        requested_parameters=dict(requested),
        applied_parameters=applied,
        defaults_applied=defaults,
        parameter_map=parameter_map,
        metadata=metadata_dict,
        fingerprint=fingerprint,
    )


def load_extraction_profile(
    path: Path,
    supported_parameters: Mapping[str, Mapping[str, Any]],
) -> ExtractionProfile:
    """Load a JSON/YAML profile and resolve it against backend capabilities."""
    path = Path(path).resolve(strict=True)
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, ImportError) as error:
        raise ExtractionProfileError(f"Cannot load extraction profile {path}: {error}") from error
    return resolve_extraction_profile(data, supported_parameters)
