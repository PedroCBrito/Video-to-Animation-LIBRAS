import sys
from pathlib import Path
from typing import Dict, Any, Optional

class FreeMoCapWrapper:
    """
    Interface to trigger 2D pose estimation, 3D reconstruction,
    and temporal smoothing using the freemocap package installed via pip.
    Fully compatible with Python 3.12+.
    """
    def __init__(self):
        pass

    def process_session(self, session_dir: Path, config: Optional[Dict[str, Any]] = None) -> Path:
        """
        Executes the 2D tracking, 3D spatial reconstruction, and Butterworth smoothing on the session.
        """
        session_dir = Path(session_dir).resolve()
        print(f"[FreeMoCapWrapper] Starting session processing: {session_dir}")

        try:
            # Import processing module from FreeMoCap
            try:
                from freemocap.core.process_recording_session import process_recording_session
                print("[FreeMoCapWrapper] Executing process_recording_session...")
                process_recording_session(recording_session_path=session_dir)
            except (ImportError, AttributeError):
                import freemocap
                print(f"[FreeMoCapWrapper] FreeMoCap v{getattr(freemocap, '__version__', 'installed')} detected.")
                if hasattr(freemocap, "process_recording_session"):
                    freemocap.process_recording_session(recording_session_path=session_dir)
                else:
                    from freemocap.core.process_recording_session import process_recording_session
                    process_recording_session(recording_session_path=session_dir)
        except (ImportError, ModuleNotFoundError) as e:
            print(f"[FreeMoCapWrapper] Error: 'freemocap' package was not found in the Python environment ({e}).", file=sys.stderr)
            print(f"[FreeMoCapWrapper] Please install dependencies using: pip install -r requirements.txt", file=sys.stderr)
            raise e

        return session_dir
