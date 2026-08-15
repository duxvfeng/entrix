"""Structural analyzer 适配器。

支持：
- 内置 Tree-sitter 分析器
- 外部 `code-review-graph` 作为可选的兼容 backend

外部 adapter 处理：
- Lazy import（仅在真正使用时）
- ROUTA_CODE_REVIEW_GRAPH_SOURCE 环境变量用于本地开发
- 未安装时优雅地报错
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from entrix.structure.builtin import BuiltinGraphAdapter


class CodeReviewGraphAdapter:
    """将 code_review_graph 包装为 StructuralAnalyzer 实现。"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self._tools = None

    def _ensure_loaded(self) -> None:
        """根据 ROUTA_CODE_REVIEW_GRAPH_SOURCE 懒加载 code_review_graph。"""
        if self._tools is not None:
            return

        source = os.environ.get("ROUTA_CODE_REVIEW_GRAPH_SOURCE")
        if source:
            sys.path.insert(0, source)

        try:
            from code_review_graph import tools as crg_tools
            self._tools = crg_tools
        except ImportError as e:
            raise ImportError(
                "code-review-graph is not installed. "
                "Install with: pip install entrix[graph]"
            ) from e

    def build_or_update(self, *, full: bool = False, base: str = "HEAD~1") -> dict:
        self._ensure_loaded()
        return self._tools.build_or_update_graph(
            repo_root=str(self.repo_root),
            base=base,
            full_rebuild=full,
        )

    def impact_radius(self, files: list[str], *, depth: int = 2) -> dict:
        self._ensure_loaded()
        return self._tools.get_impact_radius(
            changed_files=files,
            max_depth=depth,
            repo_root=str(self.repo_root),
        )

    def query(self, query_type: str, target: str) -> dict:
        self._ensure_loaded()
        return self._tools.query_graph(
            pattern=query_type,
            target=target,
            repo_root=str(self.repo_root),
        )

    def stats(self) -> dict:
        self._ensure_loaded()
        return self._tools.list_graph_stats(repo_root=str(self.repo_root))


def try_create_adapter(repo_root: Path):
    """创建当前可用的最佳 structural analyzer backend。

    Backend 选择可通过 `ROUTA_FITNESS_GRAPH_BACKEND` 强制指定：
    - `external`：要求使用 code-review-graph
    - `builtin`：始终使用本地 Tree-sitter 分析器
    - `auto`（默认）：优先使用 builtin，然后回退到 external
    """
    backend = os.environ.get("ROUTA_FITNESS_GRAPH_BACKEND", "auto").strip().lower() or "auto"

    if backend in {"auto", "builtin"}:
        try:
            return BuiltinGraphAdapter(repo_root)
        except ImportError:
            if backend == "builtin":
                return None

    if backend in {"auto", "external"}:
        adapter = CodeReviewGraphAdapter(repo_root)
        try:
            adapter._ensure_loaded()
            return adapter
        except ImportError:
            if backend == "external":
                return None

    return None
