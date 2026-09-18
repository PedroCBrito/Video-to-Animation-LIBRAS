"""Validated media preparation profiles.

The default profile is deliberately conservative: it keeps the
source cadence, removes audio that the motion pipeline does not consume, and
produces a broadly decodable MP4.  The profile can be replaced after a real
FreeMoCap recording establishes a different contract.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


class ProfileError(ValueError):
    """Raised when a preparation profile is missing or unsafe."""


@dataclass(frozen=True)
class MediaPreparationProfile:
    """FFmpeg choices that affect preparation compatibility and run identity."""

    name: str = "cp1-default"
    output_container: str = "mp4"
    video_codec: str = "libx264"
    pixel_format: str = "yuv420p"
    fps_mode: str = "preserve"
    target_fps: str | None = None
    rotation: str = "autorotate"
    remove_audio: bool = True
    preset: str = "medium"
    crf: int = 18

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "MediaPreparationProfile":
        if not isinstance(data, dict):
            raise ProfileError("Preparation profile must be a JSON/YAML object.")
        media = data.get("media", data)
        if not isinstance(media, dict):
            raise ProfileError("Preparation profile 'media' must be an object.")
        values = {
            "name": data.get("name", cls.name),
            "output_container": media.get("output_container", cls.output_container),
            "video_codec": media.get("video_codec", cls.video_codec),
            "pixel_format": media.get("pixel_format", cls.pixel_format),
            "fps_mode": media.get("fps_mode", cls.fps_mode),
            "target_fps": media.get("target_fps", cls.target_fps),
            "rotation": media.get("rotation", cls.rotation),
            "remove_audio": media.get("remove_audio", cls.remove_audio),
            "preset": media.get("preset", cls.preset),
            "crf": media.get("crf", cls.crf),
        }
        profile = cls(**values)
        profile.validate()
        return profile

    def validate(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ProfileError("Profile name must be a non-empty string.")
        if self.output_container != "mp4":
            raise ProfileError("The current preparation supports only the MP4 output container.")
        if not self.video_codec or not self.pixel_format:
            raise ProfileError("Video codec and pixel format are required.")
        if self.fps_mode not in {"preserve", "cfr"}:
            raise ProfileError("fps_mode must be 'preserve' or 'cfr'.")
        if self.fps_mode == "cfr" and not self.target_fps:
            raise ProfileError("target_fps is required when fps_mode is 'cfr'.")
        if self.target_fps is not None:
            try:
                numerator, denominator = (int(part) for part in str(self.target_fps).split("/", 1))
                if numerator <= 0 or denominator <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                raise ProfileError("target_fps must be a positive rational such as '30/1'.")
        if self.rotation not in {"autorotate", "preserve"}:
            raise ProfileError("rotation must be 'autorotate' or 'preserve'.")
        if not isinstance(self.remove_audio, bool):
            raise ProfileError("remove_audio must be boolean.")
        if self.preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast",
                               "medium", "slow", "slower", "veryslow"}:
            raise ProfileError("Unsupported x264 preset.")
        if isinstance(self.crf, bool) or not isinstance(self.crf, int) or not 0 <= self.crf <= 51:
            raise ProfileError("crf must be an integer from 0 to 51.")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {"schema_version": "1.0", **asdict(self)}

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_profile(path: Path | None = None) -> MediaPreparationProfile:
    """Load a profile, or return the explicit provisional default."""
    if path is None:
        return MediaPreparationProfile()
    path = Path(path).resolve(strict=True)
    try:
        if path.suffix.lower() == ".json":
            import json
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            try:
                import yaml
            except ImportError as error:
                raise ProfileError("PyYAML is required to load YAML preparation profiles.") from error
            data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ProfileError(f"Cannot load preparation profile {path}: {error}") from error
    return MediaPreparationProfile.from_mapping(data)
