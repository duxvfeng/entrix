"""共享的只读 git 查询，供 CLI 与 Stop Gate 复用。"""

from __future__ import annotations

import subprocess
from pathlib import Path


def current_branch(repo_root: Path, *, timeout: float = 10.0) -> str:
    """返回当前检出的分支名；仓库外或 git 不可用时返回 ``unknown``。"""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    branch = result.stdout.strip()
    return branch if result.returncode == 0 and branch else "unknown"


def find_project_root() -> Path:
    """从 CWD 向上遍历，查找常见项目或 Harness 根目录。"""
    cwd = Path.cwd().resolve()
    markers = (
        "harness.yaml",
        ".harness/harness.yaml",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    )
    for parent in [cwd, *cwd.parents]:
        if any((parent / marker).exists() for marker in markers):
            return parent
    return cwd
