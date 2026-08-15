"""Structural analyzer 的 Protocol 定义。

将 guardrail engine 与任何具体的 code graph 实现解耦。
内置 Tree-sitter 适配器是默认 backend，但 Protocol 允许
替换为其他实现（code-review-graph、远程服务等）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StructuralAnalyzer(Protocol):
    """code structure analysis backend 的接口。"""

    def build_or_update(self, *, full: bool = False, base: str = "HEAD~1") -> dict:
        """构建或增量更新 code graph。

        Returns:
            返回包含 'build_type'、'files_parsed'、'nodes'、'edges' 等键的 Dict。
        """
        ...

    def impact_radius(self, files: list[str], *, depth: int = 2) -> dict:
        """从一组 changed files 计算 blast radius。

        Returns:
            返回包含 'status'、'changed_nodes'、'impacted_nodes'、
            'impacted_files'、'edges' 的 Dict。
        """
        ...

    def query(self, query_type: str, target: str) -> dict:
        """执行 structural query (callers_of, tests_for, etc.)。

        Returns:
            返回 query-specific 结果的 Dict。
        """
        ...

    def stats(self) -> dict:
        """返回 graph 的聚合统计信息。

        Returns:
            返回包含 'nodes'、'edges'、'files'、'languages' 等键的 Dict。
        """
        ...
