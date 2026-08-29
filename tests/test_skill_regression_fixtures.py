"""Regression coverage for bundled Entrix skill fixtures."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import copytree

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "skill_regression"
ENTRIX_CMD = [sys.executable, "-m", "entrix"]

# fixture 的指标命令用裸 `python` 调解释器。CI runner 的 PATH 顺序不可控
# （macOS 镜像的框架 Python 可能排在 setup-python 之前且未装 pytest），
# 这里垫一个指向测试解释器的 shim 目录，保证指标与测试用同一解释器。
_PYTHON_SHIM_DIR = Path(tempfile.gettempdir()) / f"entrix-pyshim-{os.getpid()}"


def _python_shim_dir() -> str | None:
    if os.name == "nt":
        # Windows 的 setup-python 目录自带 python.exe，无需 shim
        return None
    _PYTHON_SHIM_DIR.mkdir(exist_ok=True)
    shim = _PYTHON_SHIM_DIR / "python"
    # 必须用 wrapper 而不是符号链接：CPython 会把符号链接一路解析到
    # 真实解释器，venv 的 python 经二次链接调用后不会激活 venv 的
    # site-packages（pytest 装在那里）。
    wrapper = f'#!/bin/sh\nexec "{sys.executable}" "$@"\n'
    if not shim.exists() or shim.read_text(encoding="utf-8") != wrapper:
        shim.write_text(wrapper, encoding="utf-8")
        shim.chmod(0o755)
    return str(_PYTHON_SHIM_DIR)


def run_entrix(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    shim_dir = _python_shim_dir()
    path_value = os.environ.get("PATH", "")
    if shim_dir:
        path_value = f"{shim_dir}{os.pathsep}{path_value}" if path_value else shim_dir
    return subprocess.run(
        [*ENTRIX_CMD, *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(project_root), "PATH": path_value},
    )


def materialize_fixture(tmp_path: Path, fixture_name: str) -> Path:
    source_root = FIXTURE_ROOT / fixture_name
    fixture_root = tmp_path / fixture_name
    copytree(source_root, fixture_root)
    subprocess.run(["git", "init", "-q"], cwd=fixture_root, check=True)
    return fixture_root


@pytest.mark.parametrize(
    ("fixture_name", "expects_agents", "expects_claude"),
    [
        ("dual-entry-local-green", True, True),
        ("claude-only-ci-boundary", False, True),
    ],
)
def test_fixture_entrypoint_topology(
    fixture_name: str, expects_agents: bool, expects_claude: bool
) -> None:
    fixture_root = FIXTURE_ROOT / fixture_name
    assert (fixture_root / "AGENTS.md").exists() is expects_agents
    assert (fixture_root / "CLAUDE.md").exists() is expects_claude


@pytest.mark.parametrize(
    "fixture_name",
    [
        "dual-entry-local-green",
        "claude-only-ci-boundary",
    ],
)
def test_fixture_repositories_validate_and_run_locally(
    tmp_path: Path, fixture_name: str
) -> None:
    fixture_root = materialize_fixture(tmp_path, fixture_name)

    for args in (
        ("validate",),
        ("run", "--dry-run"),
        ("run", "--tier", "fast"),
        ("run",),
    ):
        completed = run_entrix(fixture_root, *args)
        assert completed.returncode == 0, (
            f"{fixture_name} failed for {' '.join(args)}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def test_claude_only_fixture_ci_scope_is_executable(tmp_path: Path) -> None:
    fixture_root = materialize_fixture(tmp_path, "claude-only-ci-boundary")
    completed = run_entrix(fixture_root, "run", "--scope", "ci", "--min-score", "0")
    assert completed.returncode == 0, (
        f"claude-only-ci-boundary failed for ci scope\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
