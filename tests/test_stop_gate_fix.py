"""测试 Stop Gate 异常处理"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from entrix.stop_gate.revalidation import CachedVerdict, StopGateStateStore


def test_stop_gate_with_invalid_config() -> None:
    """测试 Stop Gate 处理无效配置：应放行（返回 0）而不是阻塞"""
    temp_dir = Path(tempfile.mkdtemp())
    invalid_config = temp_dir / "harness.yaml"
    invalid_config.write_text("invalid: yaml: content: [", encoding="utf-8")

    result = subprocess.run(
        ["python", "-m", "entrix.cli", "stop-gate"],
        cwd=temp_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
    )

    assert result.returncode == 0


def test_stop_gate_no_config() -> None:
    """测试 Stop Gate 处理没有配置的情况：应放行"""
    temp_dir = Path(tempfile.mkdtemp())

    result = subprocess.run(
        ["python", "-m", "entrix.cli", "stop-gate"],
        cwd=temp_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
    )

    assert result.returncode == 0


def test_clear_cache_script(tmp_path: Path) -> None:
    """测试缓存清理脚本：dry-run 应打印预览且不删除缓存"""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state_store = StopGateStateStore(tmp_path / "state")
    state_store.save(
        workspace,
        "session-1",
        CachedVerdict(fingerprint="f" * 64, status="fail", summary="cached verdict"),
    )

    result = subprocess.run(
        [
            "python",
            "scripts/clear_stop_gate_cache.py",
            "--repo",
            str(workspace),
            "--state-dir",
            str(tmp_path / "state"),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
    )

    assert result.returncode == 0
    assert "预览模式" in result.stdout
    assert state_store.load(workspace, "session-1") is not None
