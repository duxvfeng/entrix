"""when 谓词的条件表达式求值。"""
import os
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List


@dataclass
class WhenContext:
    """评估 when 条件的上下文。"""
    repo_root: Path = field(default_factory=Path.cwd)
    changed_files: Optional[List[str]] = None
    current_branch: Optional[str] = None

    def __post_init__(self):
        if self.changed_files is None:
            self.changed_files = []
        if self.current_branch is None:
            self.current_branch = "unknown"


def _files_exist(patterns: List[str], context: WhenContext) -> bool:
    """检查匹配模式的文件是否存在。"""
    for pattern in patterns:
        full_path = context.repo_root / pattern
        if full_path.exists():
            return True
    return False


def _changed_any(patterns: List[str], context: WhenContext) -> bool:
    """检查是否有变更文件匹配模式。"""
    if not context.changed_files:
        return False

    for pattern in patterns:
        for changed_file in context.changed_files:
            if fnmatch.fnmatch(changed_file, pattern):
                return True
    return False


def _branch(config: Dict[str, List[str]], context: WhenContext) -> bool:
    """检查分支 include/exclude 条件。"""
    include_patterns = config.get("include", [])
    exclude_patterns = config.get("exclude", [])

    # 先检查 exclude
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(context.current_branch, pattern):
            return False

    # 检查 include
    if include_patterns:
        for pattern in include_patterns:
            if fnmatch.fnmatch(context.current_branch, pattern):
                return True
        return False

    return True


def _env(required_vars: Dict[str, str], context: WhenContext) -> bool:
    """检查环境变量条件。"""
    for var_name, expected_value in required_vars.items():
        actual_value = os.environ.get(var_name)
        if actual_value != expected_value:
            return False
    return True


def evaluate_when(when: Optional[Dict[str, Any]], context: WhenContext) -> bool:
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
            # 未知谓词 - 保守地返回 False
            return False

    return True
