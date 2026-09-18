"""Inspect source media and decode the selected video stream read-only."""

from fractions import Fraction
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import time
from typing import Any, Callable

from src.common import sha256_file, utc_now
from src.ingestion.inventory import summarize


class MediaError(ValueError):
    pass


def _run(command: list[str], timeout: float) -> str:
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as error:
        raise MediaError(f"Tool timed out after {timeout:g}s: {command[0]}") from error
    except OSError as error:
        raise MediaError(f"Cannot execute {command[0]}: {error}") from error
    if result.returncode != 0:
        raise MediaError(f"Tool exited with code {result.returncode}: {result.stderr[-4000:].strip()}")
    # Commands use -v error, so even a successful return with decoder errors is not clean.
    if result.stderr.strip():
        raise MediaError(f"Tool reported errors: {result.stderr[-4000:].strip()}")
    return result.stdout


def resolve_tool(value: str) -> str:
    found = shutil.which(value)
    if not found:
        raise MediaError(f"Executable not found: {value}. Install FFmpeg/FFprobe or provide its path.")
    return str(Path(found).resolve())


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _rational(value: Any) -> str | None:
    try:
        fraction = Fraction(str(value))
        return str(fraction) if fraction > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _json_output(command: list[str], timeout: float) -> dict[str, Any]:
    try:
        data = json.loads(_run(command, timeout))
    except json.JSONDecodeError as error:
        raise MediaError("FFprobe returned invalid JSON.") from error
    if not isinstance(data, dict):
        raise MediaError("FFprobe returned an unexpected JSON structure.")
    return data


def select_video_stream(streams: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic", 0)]
    if not candidates:
        raise MediaError("No video stream found (attached cover art is not a video).")
    selected = min(candidates, key=lambda s: (
        -int(bool(s.get("disposition", {}).get("default", 0))), s["index"],
    ))
    if (not selected.get("codec_name") or selected.get("width", 0) <= 0
            or selected.get("height", 0) <= 0):
        raise MediaError("Video codec or dimensions are invalid.")
    return selected


def timestamp_summary(frames: list[dict[str, Any]], time_base: str | None) -> dict[str, Any]:
    """Keep original timestamp ticks; classify cadence from all decoded frames."""
    records = []
    for index, frame in enumerate(frames):
        pts = _integer(frame.get("pts"))
        estimated = _integer(frame.get("best_effort_timestamp"))
        records.append({
            "frame": index, "pts": pts, "best_effort_timestamp": estimated,
            "timestamp": pts if pts is not None else estimated,
            "timestamp_source": "pts" if pts is not None else (
                "best_effort_timestamp" if estimated is not None else "unavailable"),
            "duration_ticks": _integer(frame.get("duration", frame.get("pkt_duration"))),
        })
    ticks = [record["timestamp"] for record in records]
    complete = bool(ticks) and all(tick is not None for tick in ticks)
    deltas = [b - a for a, b in zip(ticks, ticks[1:])] if complete else []
    monotonic = all(delta > 0 for delta in deltas) if complete else False
    cadence = "unknown"
    # Quantized time bases can alternate adjacent tick counts even for CFR.
    tolerance_ticks = max(1.0, statistics.median(deltas) * 0.001) if deltas else None
    if time_base and complete and monotonic and len(deltas) >= 2:
        cadence = "vfr" if max(deltas) - min(deltas) > tolerance_ticks else "cfr"
    return {
        "time_base": time_base, "frames": records, "complete": complete,
        "strictly_increasing": monotonic, "cadence": cadence,
        "cadence_method": "all_decoded_frame_deltas",
        "tolerance_ticks": tolerance_ticks,
        "min_delta_ticks": min(deltas) if deltas else None,
        "max_delta_ticks": max(deltas) if deltas else None,
    }


class MediaInspector:
    def __init__(self, ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg", timeout: float = 120):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be a finite, positive number.")
        self.timeout = timeout
        self.ffprobe = resolve_tool(ffprobe)
        self.ffmpeg = resolve_tool(ffmpeg)
        self.tools = {}
        for name, executable in (("ffprobe", self.ffprobe), ("ffmpeg", self.ffmpeg)):
            version = _run([executable, "-version"], timeout).splitlines()
            if not version or not version[0].lower().startswith(name + " version"):
                raise MediaError(f"Unexpected executable for {name}: {executable}")
            self.tools[name] = {"path": executable, "version": version[0]}

    def inspect(self, path: Path) -> dict[str, Any]:
        path = path.resolve(strict=True)
        raw = _json_output([
            self.ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path),
        ], self.timeout)
        streams = raw.get("streams", [])
        selected = select_video_stream(streams)
        stream_index = selected["index"]
        frame_data = _json_output([
            self.ffprobe, "-v", "error", "-select_streams", str(stream_index),
            "-show_frames", "-show_entries",
            "frame=pts,best_effort_timestamp,duration,pkt_duration", "-of", "json", str(path),
        ], self.timeout)
        frames = frame_data.get("frames", [])
        if not frames:
            raise MediaError("Video contains no decodable frames.")
        # Decode the entire selected stream, without producing a media file.
        _run([
            self.ffmpeg, "-v", "error", "-nostdin", "-xerror", "-err_detect", "explode",
            "-i", str(path), "-map", f"0:{stream_index}", "-an", "-sn", "-dn",
            "-f", "null", "-",
        ], self.timeout)
        timeline = timestamp_summary(frames, _rational(selected.get("time_base")))
        warnings = []
        if not timeline["complete"] or not timeline["strictly_increasing"]:
            warnings.append("missing_or_non_monotonic_timestamps")
        if timeline["cadence"] == "unknown":
            warnings.append("unknown_cadence")
        declared_frames = _integer(selected.get("nb_frames"))
        if declared_frames is not None and declared_frames != len(frames):
            warnings.append("declared_and_decoded_frame_counts_differ")
        video_streams = [s for s in streams if s.get("codec_type") == "video"
                         and not s.get("disposition", {}).get("attached_pic", 0)]
        if len(video_streams) > 1:
            warnings.append("multiple_video_streams_selected_default_then_lowest_index")
        rotation = None
        rotation_source = None
        for side_data in selected.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = _number(side_data["rotation"])
                rotation_source = "display_matrix"
                break
        if rotation is None:
            rotation = _number(selected.get("tags", {}).get("rotate"))
            if rotation is not None:
                rotation_source = "rotate_tag"
        duration = _number(selected.get("duration"))
        container_duration = _number(raw.get("format", {}).get("duration"))
        if duration is None and container_duration is None:
            warnings.append("duration_unavailable")
        avg_fps = _rational(selected.get("avg_frame_rate"))
        nominal_fps = _rational(selected.get("r_frame_rate"))
        if avg_fps is None and nominal_fps is None:
            warnings.append("frame_rate_unavailable")
        return {
            "container": raw.get("format", {}).get("format_name"),
            "stream_index": stream_index, "stream_selection": "default_then_lowest_index_excluding_cover_art",
            "codec": selected["codec_name"], "pixel_format": selected.get("pix_fmt"),
            "width": selected["width"], "height": selected["height"],
            "sample_aspect_ratio": selected.get("sample_aspect_ratio"),
            "fps_average": avg_fps, "fps_nominal": nominal_fps,
            "stream_duration_seconds": duration, "container_duration_seconds": container_duration,
            "declared_frame_count": declared_frames, "decoded_frame_count": len(frames),
            "rotation_degrees": rotation, "rotation_source": rotation_source,
            "mirrored": None, "mirroring_assessment": "not_inferred",
            "timeline": timeline, "raw_probe": raw,
            "validation": {"level": "full_selected_video_decode", "decodable": True,
                           "audio_validated": False, "visual_quality_validated": False,
                           "warnings": warnings},
        }


def inspect_inventory(
    report: dict[str, Any], inspector: MediaInspector,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    report["stage"] = "inspect"
    report["tools"] = inspector.tools
    report["tool_timeout_seconds"] = inspector.timeout
    total = len(report["entries"])
    for index, entry in enumerate(report["entries"], start=1):
        if entry["status"] != "ready":
            if progress_callback is not None:
                progress_callback(index, total, entry)
            continue
        started = time.monotonic()
        try:
            source = Path(entry["source_path"])
            before = source.stat()
            if (before.st_size, before.st_mtime_ns) != (entry["size_bytes"], entry["mtime_ns"]):
                raise MediaError("Source changed since inventory; run again.")
            entry["inspection"] = inspector.inspect(source)
            if sha256_file(source) != entry["sha256"]:
                raise MediaError("Source content changed during inspection; run again.")
            warnings = entry["inspection"]["validation"]["warnings"]
            entry.update(status="review" if warnings else "valid",
                         reason="; ".join(warnings) if warnings else None)
        except (OSError, ValueError) as error:
            entry.update(status="invalid", reason=str(error))
            entry["inspection"] = {"validation": {
                "level": "failed", "decodable": None,
                "visual_quality_validated": False, "error": str(error),
            }}
        entry["inspection_seconds"] = round(time.monotonic() - started, 6)
        if progress_callback is not None:
            progress_callback(index, total, entry)
    report["finished_at"] = utc_now()
    summarize(report)
    return report
