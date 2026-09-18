"""FFmpeg execution and atomic publication for prepared videos."""

import os
from pathlib import Path
import subprocess
from typing import Any

from src.preparation.profile import MediaPreparationProfile


class PreparationError(ValueError):
    """Raised when FFmpeg cannot produce a valid prepared video."""


def build_command(
    source: Path, destination: Path, profile: MediaPreparationProfile,
) -> list[str]:
    """Build an argv list without shell interpolation."""
    profile.validate()
    command = [
        "ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-y",
    ]
    if profile.rotation == "preserve":
        command.append("-noautorotate")
    command += ["-i", str(source), "-map", "0:v:0", "-sn", "-dn"]
    command += ["-c:v", profile.video_codec, "-pix_fmt", profile.pixel_format]
    if profile.fps_mode == "preserve":
        command += ["-fps_mode", "passthrough"]
    else:
        command += ["-fps_mode", "cfr", "-r", str(profile.target_fps)]
    if profile.video_codec == "libx264":
        command += ["-preset", profile.preset, "-crf", str(profile.crf)]
    if profile.remove_audio:
        command.append("-an")
    else:
        command += ["-c:a", "aac"]
    command += ["-map_metadata", "0", str(destination)]
    return command


def run_ffmpeg(
    source: Path, destination: Path, profile: MediaPreparationProfile,
    *, ffmpeg: str = "ffmpeg", timeout: float = 120,
) -> dict[str, Any]:
    """Encode to a temporary sibling and publish only a completed file."""
    if timeout <= 0:
        raise ValueError("FFmpeg timeout must be positive.")
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if source == destination:
        raise PreparationError("Prepared video must be different from the source.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep the media suffix so FFmpeg can infer the output container while the
    # file remains clearly unpublished until the atomic replace below.
    temporary = destination.with_name(destination.stem + ".part" + destination.suffix)
    temporary.unlink(missing_ok=True)
    command = build_command(source, temporary, profile)
    command[0] = str(Path(ffmpeg).resolve()) if Path(ffmpeg).exists() else ffmpeg
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as error:
        temporary.unlink(missing_ok=True)
        raise PreparationError(f"FFmpeg timed out after {timeout:g}s.") from error
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise PreparationError(f"Cannot execute FFmpeg: {error}") from error
    if result.returncode != 0 or result.stderr.strip():
        temporary.unlink(missing_ok=True)
        message = result.stderr[-4000:].strip() or f"exit code {result.returncode}"
        raise PreparationError(f"FFmpeg failed: {message}")
    if not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise PreparationError("FFmpeg completed without producing a non-empty file.")
    os.replace(temporary, destination)
    return {"command": command, "size_bytes": destination.stat().st_size}
