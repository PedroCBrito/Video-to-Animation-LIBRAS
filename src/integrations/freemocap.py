"""FreeMoCap process adapter reserved for a future integration."""

import sys
from pathlib import Path
from typing import Any


class FreeMoCapAdapter:
    """Invoke the installed FreeMoCap API once its contract is fixed."""

    def process_session(self, session_dir: Path, config: dict[str, Any] | None = None) -> Path:
        session_dir = Path(session_dir).resolve()
        print(f"[FreeMoCapAdapter] Starting session processing: {session_dir}")
        try:
            try:
                from freemocap.core.process_recording_session import process_recording_session
                print("[FreeMoCapAdapter] Executing process_recording_session...")
                process_recording_session(recording_session_path=session_dir)
            except (ImportError, AttributeError):
                import freemocap
                print(f"[FreeMoCapAdapter] FreeMoCap v{getattr(freemocap, '__version__', 'installed')} detected.")
                if hasattr(freemocap, "process_recording_session"):
                    freemocap.process_recording_session(recording_session_path=session_dir)
                else:
                    from freemocap.core.process_recording_session import process_recording_session
                    process_recording_session(recording_session_path=session_dir)
        except (ImportError, ModuleNotFoundError) as error:
            print(f"[FreeMoCapAdapter] FreeMoCap is unavailable ({error}).", file=sys.stderr)
            print("[FreeMoCapAdapter] Install dependencies with: pip install -r requirements.txt", file=sys.stderr)
            raise
        return session_dir
