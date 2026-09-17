import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from src.video_processor import VideoProcessor
from src.freemocap_wrapper import FreeMoCapWrapper
from src.blender_exporter import BlenderExporter

class PipelineOrchestrator:
    """
    Core orchestrator of the Video-to-Animation pipeline.
    Integrates video ingestion, FreeMoCap markerless motion capture, and headless Blender export.
    """
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        
        self.config_path = Path(config_path).resolve()
        self.config = self._load_config()

        self.blender_exe = self._resolve_blender_exe()

        self.freemocap_wrapper = FreeMoCapWrapper()
        self.blender_exporter = BlenderExporter(blender_executable=self.blender_exe)

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _resolve_blender_exe(self) -> Path:
        primary = Path(self.config["blender"]["executable"])
        if primary.exists():
            return primary
        
        for fallback in self.config["blender"].get("fallback_paths", []):
            p = Path(fallback)
            if p.exists():
                print(f"[Orchestrator] Using fallback Blender executable path: {p}")
                return p
        
        return primary

    def run(self, video_path: Path, output_dir: Path, session_name: str = "session_001") -> Path:
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n==================================================")
        print(f"🚀 STARTING VIDEO-TO-ANIMATION PIPELINE")
        print(f"==================================================\n")

        # 1. Video Ingestion & Preparation
        video_processor = VideoProcessor(session_base_dir=output_dir / "sessions")
        session_info = video_processor.prepare_session(video_path=video_path, session_name=session_name)
        session_dir = session_info["session_dir"]

        # 2. FreeMoCap 2D/3D Processing
        processed_session = self.freemocap_wrapper.process_session(session_dir=session_dir, config=self.config.get("processing"))

        # 3. Headless Blender Export
        output_blend = output_dir / f"{session_name}_animation.blend"
        result_path = self.blender_exporter.export_animation(session_dir=processed_session, output_blend_path=output_blend)

        print(f"\n==================================================")
        print(f"✅ PIPELINE COMPLETED SUCCESSFULLY!")
        print(f"📁 Animation saved to: {result_path}")
        print(f"==================================================\n")

        return result_path
