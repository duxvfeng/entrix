"""when 谓词的条件表达式求值。"""
from __future__ import annotations

import fnmatch
import ntpath
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PREDICATES = frozenset({"files_exist", "changed_any", "branch", "env"})


@dataclass
class WhenContext:
    """评估 when 条件的上下文。"""

    repo_root: Path = field(default_factory=Path.cwd)
    changed_files: list[str] | None = None
    current_branch: str | None = None

    def __post_init__(self) -> None:
        if self.changed_files is None:
            self.changed_files = []
        if self.current_branch is None:
            self.current_branch = "unknown"


def _validated_pattern(pattern: object, context: WhenContext) -> str:
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("when 路径模式必须是非空字符串")
    relative_path = Path(pattern)
    root = context.repo_root.resolve()
    # Windows drive paths must remain invalid on POSIX runners too.
    if relative_path.is_absolute() or ntpath.isabs(pattern):
        raise ValueError(f"when 路径必须位于工作区内：{pattern}")
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"when 路径必须位于工作区内：{pattern}")
    return pattern


def _files_exist(patterns: list[str], context: WhenContext) -> bool:
    """检查匹配模式的文件是否存在。"""
    for pattern in patterns:
        normalized = _validated_pattern(pattern, context)
        if any(context.repo_root.glob(normalized)):
            return True
    return False


def _changed_any(patterns: list[str], context: WhenContext) -> bool:
    """检查是否有变更文件匹配模式。"""
    if not context.changed_files:
        return False

    for pattern in patterns:
        for changed_file in context.changed_files:
            if fnmatch.fnmatch(changed_file, pattern):
                return True
    return False


def _branch(config: dict[str, list[str]], context: WhenContext) -> bool:
    """检查分支 include/exclude 条件。"""
    include_patterns = config.get("include", [])
    exclude_patterns = config.get("exclude", [])
    current_branch = context.current_branch
    if current_branch is None:
        current_branch = "unknown"

    # 先检查 exclude
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(current_branch, pattern):
            return False

    # 检查 include
    if include_patterns:
        for pattern in include_patterns:
            if fnmatch.fnmatch(current_branch, pattern):
                return True
        return False

    return True


def _env(required_vars: dict[str, str], context: WhenContext) -> bool:
    """检查环境变量条件。"""
    for var_name, expected_value in required_vars.items():
        actual_value = os.environ.get(var_name)
        if actual_value != expected_value:
            return False
    return True


def validate_when_config(when: object, field_name: str) -> dict[str, Any] | None:
    """Validate one declarative activation block."""
    if when is None:
        return None
    if not isinstance(when, dict):
        raise ValueError(f"{field_name} 必须是对象")
    for predicate, value in when.items():
        if predicate not in _PREDICATES:
            raise ValueError(f"未知 when 谓词：{predicate}")
        if predicate in {"files_exist", "changed_any"}:
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item for item in value
            ):
                raise ValueError(f"{field_name}.{predicate} 必须是非空字符串列表")
        elif predicate == "branch":
            if not isinstance(value, dict):
                raise ValueError(f"{field_name}.branch 必须是对象")
            unknown = set(value) - {"include", "exclude"}
            if unknown:
                raise ValueError(f"未知 branch 条件：{sorted(unknown)[0]}")
            for key, patterns in value.items():
                if not isinstance(patterns, list) or not all(
                    isinstance(item, str) and item for item in patterns
                ):
                    raise ValueError(f"{field_name}.branch.{key} 必须是字符串列表")
        elif predicate == "env":
            if not isinstance(value, dict) or not all(
                isinstance(key, str) and isinstance(expected, str)
                for key, expected in value.items()
            ):
                raise ValueError(f"{field_name}.env 必须是字符串映射")
    return dict(when)


def evaluate_when(when: dict[str, Any] | None, context: WhenContext) -> bool:
    """评估 when 条件。

    Args:
        when: 条件字典或 None
        context: 评估上下文

    Returns:
        如果条件满足（或 when 为 None/空）则返回 True，否则返回 False
    """
    if when is None or not when:
        return True

    # when 块中的所有谓词都是 AND 关系
    for predicate_name, predicate_value in when.items():
        if predicate_name == "files_exist":
            if not _files_exist(predicate_value, context):
                return False
        elif predicate_name == "changed_any":
            if not _changed_any(predicate_value, context):
                return False
        elif predicate_name == "branch":
            if not _branch(predicate_value, context):
                return False
        elif predicate_name == "env":
            if not _env(predicate_value, context):
                return False
        else:
            raise ValueError(f"未知 when 谓词：{predicate_name}")

    return True
