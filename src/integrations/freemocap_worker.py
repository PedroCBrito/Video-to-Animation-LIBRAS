"""Worker process that calls a configured FreeMoCap Python entrypoint."""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
from pathlib import Path
from typing import Any


def _load_entrypoint(value: str):
    try:
        module_name, function_name = value.split(":", 1)
        module = importlib.import_module(module_name)
        return getattr(module, function_name)
    except (ValueError, ImportError, AttributeError) as error:
        raise RuntimeError(f"Invalid FreeMoCap entrypoint {value}: {error}") from error


def invoke_entrypoint(
    entrypoint: str,
    session_dir: Path,
    session_argument: str,
    options: dict[str, Any],
) -> Any:
    """Invoke only parameters accepted by the configured backend function."""
    function = _load_entrypoint(entrypoint)
    signature = inspect.signature(function)
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD
                         for parameter in signature.parameters.values())
    if session_argument not in signature.parameters and not accepts_kwargs:
        raise RuntimeError(f"Entrypoint does not accept '{session_argument}'.")
    accepted = dict(options) if accepts_kwargs else {
        name: value for name, value in options.items() if name in signature.parameters
    }
    accepted[session_argument] = str(session_dir)
    return function(**accepted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a configured FreeMoCap entrypoint in a worker process.")
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--session-argument", required=True)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args(argv)
    options: dict[str, Any] = {}
    if args.config:
        options = json.loads(args.config.read_text(encoding="utf-8"))
    invoke_entrypoint(args.entrypoint, args.session.resolve(), args.session_argument, options)
    print(f"FreeMoCap session completed: {args.session.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
