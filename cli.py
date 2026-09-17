import argparse
import sys
from pathlib import Path

# Adiciona o diretório atual ao sys.path para garantir importações relativas
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from src.orchestrator import PipelineOrchestrator

def main():
    parser = argparse.ArgumentParser(
        description="FreeMoCap Video-to-Animation: Converte vídeos 2D em animações 3D usando FreeMoCap e Blender."
    )
    parser.add_argument(
        "--video", "-v",
        type=str,
        required=True,
        help="Caminho para o arquivo de vídeo de entrada (.mp4, .mov, .avi)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./output",
        help="Diretório onde a animação e arquivos de saída serão salvos (padrão: ./output)"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Caminho para o arquivo de configuração personalizado (opcional)"
    )

    args = parser.parse_args()

    video_path = Path(args.video)
    output_dir = Path(args.output_dir)
    config_path = Path(args.config) if args.config else None

    try:
        orchestrator = PipelineOrchestrator(config_path=config_path)
        orchestrator.run(video_path=video_path, output_dir=output_dir)
    except Exception as e:
        print(f"\n❌ ERRO NO PIPELINE: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
