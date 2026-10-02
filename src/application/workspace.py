"""Protect one CP3 output from concurrent writers; OS releases locks on exit."""
from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path

from src.ingestion.contracts import validate_paths


@contextmanager
def output_lock(output: Path):
    internal = Path(output).resolve() / ".pipeline"
    internal.mkdir(parents=True, exist_ok=True)
    with (internal / ".lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("Já existe um processamento nesta pasta de saída. Aguarde sua conclusão.") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def exclusive_retarget(function):
    @wraps(function)
    def wrapped(source, output, stage, **options):
        if stage != "retarget":
            return function(source, output, stage, **options)
        paths = validate_paths(Path(source), Path(output), directory=Path(source).is_dir())
        with output_lock(paths.output):
            return function(source, output, stage, **options)
    return wrapped
