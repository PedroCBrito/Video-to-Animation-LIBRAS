"""Local caches for backend processes, without changing the frontend environment."""
from pathlib import Path


def backend_environment(folder: Path) -> dict[str, str]:
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / "temp"
    temporary.mkdir(exist_ok=True)
    return {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPYCACHEPREFIX": str(folder / "python-cache"),
        "TMP": str(temporary),
        "TEMP": str(temporary),
        "USERPROFILE": str(folder),
        "YOLO_CONFIG_DIR": str(folder / "ultralytics"),
        "BLENDER_USER_CONFIG": str(folder / "blender"),
    }
