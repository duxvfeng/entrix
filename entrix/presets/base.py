"""用于 repository 专用 fitness 行为的 preset protocol。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from entrix.model import Metric


class ProjectPreset(Protocol):
    """用于自定义 fitness 行为的 repository 专用 hook。"""

    def release_trigger_config(self, project_root: Path) -> Path:
        """返回该项目的默认 release-trigger config 路径。"""

    def should_ignore_changed_file(self, file_path: str) -> bool:
        """当变更文件应从增量 fitness 逻辑中排除时返回 True。"""

    def domains_from_files(self, files: list[str]) -> set[str]:
        """从文件路径推断变更 domain。"""

    def metric_domains(self, metric: Metric) -> set[str]:
        """为 fallback 变更匹配推断 metric domain。"""
