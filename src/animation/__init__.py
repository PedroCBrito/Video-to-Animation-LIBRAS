"""Animation artifacts produced after extraction."""

from src.animation.source_skeleton import SourceSkeletonError, SourceSkeletonResult, export_source_skeleton
from src.animation.avatar_inventory import AvatarInventoryError, AvatarInventoryResult, inspect_avatar
from src.animation.rig_map import RigMapError, RigMapResult, validate_rig_map, write_rig_map_report
from src.animation.retarget_stage import retarget_inventory, retarget_exit_code

__all__ = [
    "SourceSkeletonError", "SourceSkeletonResult", "export_source_skeleton",
    "AvatarInventoryError", "AvatarInventoryResult", "inspect_avatar",
    "RigMapError", "RigMapResult", "validate_rig_map", "write_rig_map_report",
    "retarget_inventory", "retarget_exit_code",
]
