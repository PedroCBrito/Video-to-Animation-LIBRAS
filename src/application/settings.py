"""Machine-local tool paths shared by the two frontends."""
import json
from pathlib import Path

from src.common import write_json_atomic

TOOLS_FILE = Path(__file__).resolve().parents[2] / "config/tool-paths.local.json"
TOOL_KEYS = {"BLENDER_BIN", "FFMPEG_BIN", "FFPROBE_BIN"}


def load_tool_paths(path: Path = TOOLS_FILE) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(k not in TOOL_KEYS or not isinstance(v, str) for k, v in data.items()):
        raise ValueError(f"Configuração local de ferramentas inválida: {path}")
    return data


def save_tool_paths(paths: dict[str, str], path: Path = TOOLS_FILE) -> None:
    write_json_atomic(path, {k: str(v) for k, v in paths.items() if k in TOOL_KEYS})
