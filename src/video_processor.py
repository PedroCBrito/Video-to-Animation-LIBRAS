import shutil
from pathlib import Path
from typing import Dict, Any

class VideoProcessor:
    """
    Responsável pela validação, ingestão e preparação do vídeo de entrada
    na estrutura de sessão esperada pelo FreeMoCap Backend Server.
    """
    def __init__(self, session_base_dir: Path):
        self.session_base_dir = Path(session_base_dir)

    def prepare_session(self, video_path: Path, session_name: str = "session_001") -> Dict[str, Path]:
        """
        Valida o vídeo de entrada e cria a estrutura de diretórios esperada:
        <session_dir>/raw_data/synchronized_videos/camera_01.mp4
        """
        video_path = Path(video_path).resolve()
        if not video_path.exists():
            raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {video_path}")
        
        valid_extensions = {".mp4", ".mov", ".avi", ".mkv"}
        if video_path.suffix.lower() not in valid_extensions:
            raise ValueError(f"Formato de vídeo não suportado: {video_path.suffix}. Formatos válidos: {valid_extensions}")

        session_dir = self.session_base_dir / session_name
        videos_dir = session_dir / "raw_data" / "synchronized_videos"
        videos_dir.mkdir(parents=True, exist_ok=True)

        target_video_path = videos_dir / f"camera_01{video_path.suffix.lower()}"
        print(f"[VideoProcessor] Copiando vídeo de entrada para: {target_video_path}")
        shutil.copy2(video_path, target_video_path)

        return {
            "session_dir": session_dir,
            "video_path": target_video_path
        }
