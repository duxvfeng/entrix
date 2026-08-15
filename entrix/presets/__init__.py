"""用于 repository 专用 fitness 行为的 project preset。"""

from entrix.presets.base import ProjectPreset
from entrix.presets.routa import RoutaPreset


def get_project_preset() -> ProjectPreset:
    """返回当前激活的 project preset。"""
    return RoutaPreset()
