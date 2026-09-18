"""Launch the simple graphical frontend."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from src.ui import main


if __name__ == "__main__":
    main()
