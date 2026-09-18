"""Media preparation for the ingestion pipeline.

The package keeps FFmpeg policy and staging separate from discovery and media
inspection.  It produces deterministic, self-contained artifacts under the
run workspace and never writes to source media.
"""

from src.preparation.pipeline import prepare_inventory, preparation_exit_code
from src.preparation.profile import MediaPreparationProfile, load_profile

__all__ = [
    "MediaPreparationProfile",
    "load_profile",
    "prepare_inventory",
    "preparation_exit_code",
]
