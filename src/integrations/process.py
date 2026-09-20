"""Controlled subprocess execution for external pipeline backends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Any, Sequence


@dataclass(frozen=True)
class ProcessResult:
    """Complete result of an external process, including controlled stops."""

    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool = False
    cancelled: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.cancelled


def _finish_process(process: subprocess.Popen[str], *, timeout: float = 5) -> tuple[str, str]:
    """Stop a process and collect remaining output without hanging forever."""
    try:
        process.terminate()
    except OSError:
        pass
    try:
        return process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        return process.communicate()


def run_process(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    cancel_event: Any | None = None,
    poll_seconds: float = 0.05,
) -> ProcessResult:
    """Run an argv command with timeout and cooperative cancellation.

    The command is always passed as an argument list. The backend receives no
    shell and therefore cannot reinterpret paths or profile values as syntax.
    """
    if timeout <= 0:
        raise ValueError("Process timeout must be positive.")
    argv = tuple(str(value) for value in command)
    if not argv:
        raise ValueError("Process command cannot be empty.")
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            list(argv), cwd=str(Path(cwd).resolve()), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        elapsed = time.monotonic() - started
        return ProcessResult(argv, None, "", str(error), elapsed)

    while process.poll() is None:
        elapsed = time.monotonic() - started
        if cancel_event is not None and cancel_event.is_set():
            stdout, stderr = _finish_process(process)
            return ProcessResult(argv, process.returncode, stdout, stderr, elapsed, cancelled=True)
        if elapsed >= timeout:
            stdout, stderr = _finish_process(process)
            return ProcessResult(argv, process.returncode, stdout, stderr, elapsed, timed_out=True)
        time.sleep(poll_seconds)

    stdout, stderr = process.communicate()
    return ProcessResult(
        argv, process.returncode, stdout, stderr, time.monotonic() - started,
    )
