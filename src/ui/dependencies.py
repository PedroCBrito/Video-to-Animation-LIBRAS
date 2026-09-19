"""Preflight checks for external tools required by the graphical workflow."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import shutil
import string
from collections.abc import Mapping
from typing import Callable


@dataclass(frozen=True)
class DependencyStatus:
    """Result of checking one dependency without changing the environment."""

    key: str
    label: str
    available: bool
    detail: str
    location: str | None
    download_url: str


DependencyFinder = Callable[[str], str | None]
ModuleFinder = Callable[[str], object | None]
BlenderDiscoverer = Callable[[], str | None]


DEPENDENCY_DEFINITIONS = (
    {
        "key": "ffmpeg",
        "label": "FFmpeg",
        "environment": "FFMPEG_BIN",
        "names": ("ffmpeg", "ffmpeg.exe"),
        "download_url": "https://ffmpeg.org/download.html",
    },
    {
        "key": "ffprobe",
        "label": "FFprobe",
        "environment": "FFPROBE_BIN",
        "names": ("ffprobe", "ffprobe.exe"),
        "download_url": "https://ffmpeg.org/download.html",
    },
    {
        "key": "freemocap",
        "label": "FreeMoCap (pacote Python)",
        "download_url": "https://www.freemocap.org/download.html",
    },
    {
        "key": "blender",
        "label": "Blender",
        "environment": "BLENDER_BIN",
        "names": ("blender", "blender.exe"),
        "download_url": "https://www.blender.org/download/",
    },
)


def _find_executable(
    definition: dict[str, object],
    environment: Mapping[str, str],
    which: DependencyFinder,
) -> tuple[str | None, str]:
    environment_name = definition.get("environment")
    if isinstance(environment_name, str) and environment.get(environment_name):
        configured = Path(environment[environment_name]).expanduser()
        if configured.is_file():
            return str(configured.resolve()), f"Encontrado pelo caminho {environment_name}."
        return None, f"{environment_name} aponta para um arquivo inexistente: {configured}"

    names = definition.get("names", ())
    for name in names if isinstance(names, tuple) else ():
        found = which(str(name))
        if found:
            return str(Path(found).resolve()), "Encontrado no PATH."
    return None, "Não encontrado no PATH."


def _windows_blender_candidates() -> list[Path]:
    """Find common Blender installations without recursively scanning disks."""
    if os.name != "nt":
        return []
    candidates: list[Path] = []

    # The Blender installer commonly registers this App Paths entry.
    try:
        import winreg
        registry_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\blender.exe"
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for access in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(root, registry_path, 0, winreg.KEY_READ | access) as key:
                        value, _ = winreg.QueryValueEx(key, None)
                        if isinstance(value, str):
                            candidates.append(Path(value.strip('"')))
                except (FileNotFoundError, OSError):
                    continue
    except (ImportError, AttributeError):
        pass

    roots: list[Path] = []
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        value = os.environ.get(variable)
        if value:
            roots.append(Path(value))
    # An installation on D:, E:, etc. is not represented by the C: env vars.
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        try:
            if drive.is_dir():
                roots.extend((drive, drive / "Program Files", drive / "Program Files (x86)", drive / "Apps"))
        except OSError:
            continue

    for root in roots:
        candidates.extend((
            root / "Blender Foundation" / "Blender" / "blender.exe",
            root / "Blender" / "blender.exe",
            root / "Steam" / "steamapps" / "common" / "Blender" / "blender.exe",
        ))
        try:
            candidates.extend(root.glob("Blender Foundation/Blender*/blender.exe"))
            candidates.extend(root.glob("Blender*/blender.exe"))
            candidates.extend(root.glob("Blender*/Blender*/blender.exe"))
        except OSError:
            continue
    return candidates


def discover_blender() -> str | None:
    """Return the first existing Blender executable found by Windows heuristics."""
    for candidate in _windows_blender_candidates():
        try:
            if candidate.is_file():
                return str(candidate.resolve())
        except OSError:
            continue
    return None


def check_dependencies(
    *,
    environment: Mapping[str, str] | None = None,
    which: DependencyFinder = shutil.which,
    module_finder: ModuleFinder = importlib.util.find_spec,
    blender_discoverer: BlenderDiscoverer = discover_blender,
) -> tuple[DependencyStatus, ...]:
    """Check required tools and Python package availability.

    The function is intentionally side-effect free so the UI can refresh the
    result before every run and tests can provide deterministic finders.
    """
    if environment is None:
        environment = os.environ
    statuses: list[DependencyStatus] = []
    for definition in DEPENDENCY_DEFINITIONS:
        key = str(definition["key"])
        label = str(definition["label"])
        url = str(definition["download_url"])
        if key == "freemocap":
            try:
                module = module_finder("freemocap")
            except (ImportError, ModuleNotFoundError):
                module = None
            available = module is not None
            statuses.append(DependencyStatus(
                key, label, available,
                "Pacote Python encontrado no ambiente atual." if available
                else "Pacote Python não encontrado neste ambiente.",
                None, url,
            ))
            continue

        location, detail = _find_executable(definition, environment, which)
        if key == "blender" and location is None and not environment.get("BLENDER_BIN"):
            discovered = blender_discoverer()
            if discovered and Path(discovered).is_file():
                location = str(Path(discovered).resolve())
                detail = "Encontrado em uma instalação do Windows."
            elif key == "blender":
                detail = "Não encontrado no PATH ou em instalações comuns; use Localizar ou BLENDER_BIN."
        statuses.append(DependencyStatus(key, label, location is not None, detail, location, url))
    return tuple(statuses)


def missing_dependencies(statuses: tuple[DependencyStatus, ...] | list[DependencyStatus]) -> list[DependencyStatus]:
    """Return missing dependencies in display order."""
    return [status for status in statuses if not status.available]
