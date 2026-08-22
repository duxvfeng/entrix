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


def test_default_state_store_is_external_to_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    external = tmp_path / "user-state"
    monkeypatch.setenv("ENTRIX_STATE_DIR", str(external))

    store = StopGateStateStore()
    store.save(
        workspace,
        "session-1",
        CachedVerdict(fingerprint="f" * 64, status="fail", summary="cached verdict"),
    )

    assert not (workspace / ".stop-gate-state").exists()
    assert not (workspace / ".harness" / "evidence").exists()
    assert list(external.rglob("*.json"))


def test_harness_trust_is_invalidated_when_config_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    config = workspace / "harness.yaml"
    config.write_text("version: harness/v1\n", encoding="utf-8")
    store = StopGateStateStore(tmp_path / "state")

    assert store.is_config_trusted(workspace, config) is False
    store.trust_config(workspace, config)
    assert store.is_config_trusted(workspace, config) is True
    config.write_text("version: harness/v1\nsettings: {failure_mode: closed}\n", encoding="utf-8")
    assert store.is_config_trusted(workspace, config) is False
