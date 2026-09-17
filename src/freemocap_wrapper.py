import sys
from pathlib import Path
from typing import Dict, Any, Optional

class FreeMoCapWrapper:
    """
    Interface para disparar a estimativa de pose 2D, reconstrução 3D
    e pós-processamento utilizando o pacote freemocap instalado via pip.
    Totalmente compatível com Python 3.12+.
    """
    def __init__(self):
        pass

    def process_session(self, session_dir: Path, config: Optional[Dict[str, Any]] = None) -> Path:
        """
        Executa o pipeline de rastreamento 2D, reconstrução 3D e filtragem de suavização na sessão.
        """
        session_dir = Path(session_dir).resolve()
        print(f"[FreeMoCapWrapper] Iniciando processamento da sessão: {session_dir}")

        try:
            # Importa o módulo de processamento do FreeMoCap
            try:
                from freemocap.core.process_recording_session import process_recording_session
                print("[FreeMoCapWrapper] Executando process_recording_session...")
                process_recording_session(recording_session_path=session_dir)
            except (ImportError, AttributeError):
                import freemocap
                print(f"[FreeMoCapWrapper] FreeMoCap v{getattr(freemocap, '__version__', 'instalado')} detectado.")
                if hasattr(freemocap, "process_recording_session"):
                    freemocap.process_recording_session(recording_session_path=session_dir)
                else:
                    from freemocap.core.process_recording_session import process_recording_session
                    process_recording_session(recording_session_path=session_dir)
        except (ImportError, ModuleNotFoundError) as e:
            print(f"[FreeMoCapWrapper] Erro: O pacote 'freemocap' não foi encontrado no ambiente Python ({e}).", file=sys.stderr)
            print(f"[FreeMoCapWrapper] Instale com: pip install freemocap ou pip install -r requirements.txt", file=sys.stderr)
            raise e

        return session_dir
