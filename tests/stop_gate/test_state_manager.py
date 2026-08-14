from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from entrix.stop_gate.errors import SystemError
from entrix.stop_gate.model import AttemptStatus, GateAttempt
from entrix.stop_gate.state_manager import SessionStateManager


def test_create_attempt(tmp_path: Path):
    """测试创建新尝试"""
    manager = SessionStateManager(state_dir=tmp_path / "state")

    attempt = GateAttempt(
        attempt_id="test-uuid",
        session_id="session-1",
        task_id="task-1",
        workspace=Path("/test"),
        base_ref="HEAD~1",
        changed_files=["src/test.py"],
        requested_at=datetime.now(timezone.utc),
        stop_reason="agent_completed",
    )

    attempt_id = manager.create_attempt(attempt)
    assert attempt_id == "test-uuid"
    assert "test-uuid" in manager.active_attempts
    assert manager.active_attempts["test-uuid"].status == AttemptStatus.REQUESTED


def test_update_attempt_status(tmp_path: Path):
    """测试更新尝试状态"""
    manager = SessionStateManager(state_dir=tmp_path / "state")

    attempt = GateAttempt(
        attempt_id="test-uuid",
        session_id="session-1",
        task_id="task-1",
        workspace=Path("/test"),
        base_ref=None,
        changed_files=[],
        requested_at=datetime.now(timezone.utc),
        stop_reason="test",
    )

    manager.create_attempt(attempt)
    manager.update_attempt_status("test-uuid", AttemptStatus.COLLECTING)

    state = manager.get_attempt("test-uuid")
    assert state.status == AttemptStatus.COLLECTING
    assert state.updated_at is not None


def test_persist_and_recover_state(tmp_path: Path):
    """测试状态持久化和恢复"""
    state_dir = tmp_path / "state"
    manager1 = SessionStateManager(state_dir=state_dir)

    attempt = GateAttempt(
        attempt_id="test-uuid",
        session_id="session-1",
        task_id="task-1",
        workspace=Path("/test"),
        base_ref=None,
        changed_files=[],
        requested_at=datetime.now(timezone.utc),
        stop_reason="test",
    )

    manager1.create_attempt(attempt)
    manager1.update_attempt_status("test-uuid", AttemptStatus.COLLECTING)

    # 创建新管理器，应该能恢复状态
    manager2 = SessionStateManager(state_dir=state_dir)
    assert "test-uuid" in manager2.active_attempts

    state = manager2.get_attempt("test-uuid")
    assert state is not None
    assert state.status == AttemptStatus.COLLECTING
    assert state.attempt_data is not None
    assert state.attempt_data.task_id == "task-1"


def test_persist_and_recover_full_attempt_data(tmp_path: Path):
    """测试完整 GateAttempt 数据的持久化和恢复"""
    state_dir = tmp_path / "state"
    manager1 = SessionStateManager(state_dir=state_dir)

    attempt = GateAttempt(
        attempt_id="test-uuid-2",
        session_id="session-2",
        task_id="task-2",
        workspace=Path("/test/workspace"),
        base_ref="HEAD~1",
        changed_files=["src/main.py", "tests/test_main.py"],
        requested_at=datetime.now(timezone.utc),
        stop_reason="agent_completed",
    )

    manager1.create_attempt(attempt)

    manager2 = SessionStateManager(state_dir=state_dir)
    state = manager2.get_attempt("test-uuid-2")
    assert state is not None
    assert state.attempt_data is not None
    assert state.attempt_data.workspace == Path("/test/workspace")
    assert state.attempt_data.changed_files == ["src/main.py", "tests/test_main.py"]
    assert state.attempt_data.base_ref == "HEAD~1"


def test_cleanup_expired_attempts(tmp_path: Path):
    """测试清理过期尝试"""
    state_dir = tmp_path / "state"
    manager = SessionStateManager(state_dir=state_dir)

    attempt = GateAttempt(
        attempt_id="old-uuid",
        session_id="session-1",
        task_id="task-1",
        workspace=Path("/test"),
        base_ref=None,
        changed_files=[],
        requested_at=datetime.now(timezone.utc),
        stop_reason="test",
    )
    manager.create_attempt(attempt)

    # 模拟过期：将 created_at 设置为 25 小时前
    old_time = datetime.now(timezone.utc) - timedelta(hours=25)
    manager.active_attempts["old-uuid"].created_at = old_time

    expired = manager.cleanup_expired_attempts(max_age_hours=24)
    assert "old-uuid" in expired
    assert "old-uuid" not in manager.active_attempts


def test_update_attempt_status_not_found(tmp_path: Path):
    """测试更新不存在的尝试会报错"""
    manager = SessionStateManager(state_dir=tmp_path / "state")
    with pytest.raises(ValueError, match="Attempt missing-uuid 不存在"):
        manager.update_attempt_status("missing-uuid", AttemptStatus.COLLECTING)


def test_session_stats_updated(tmp_path: Path):
    """测试会话统计更新"""
    state_dir = tmp_path / "state"
    manager = SessionStateManager(state_dir=state_dir)

    attempt = GateAttempt(
        attempt_id="stats-uuid",
        session_id="session-1",
        task_id="task-1",
        workspace=Path("/test"),
        base_ref=None,
        changed_files=[],
        requested_at=datetime.now(timezone.utc),
        stop_reason="test",
    )
    manager.create_attempt(attempt)
    assert manager.total_attempts == 1

    manager.update_attempt_status("stats-uuid", AttemptStatus.PASSED)
    assert manager.passed_attempts == 1

    manager2 = SessionStateManager(state_dir=state_dir)
    assert manager2.total_attempts == 1
    assert manager2.passed_attempts == 1


def test_recover_from_corrupted_state(tmp_path: Path, capsys):
    """测试从损坏的状态文件恢复时使用干净状态"""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "state.json"
    state_file.write_text("not valid json", encoding="utf-8")

    manager = SessionStateManager(state_dir=state_dir)
    assert manager.active_attempts == {}

    captured = capsys.readouterr()
    assert "状态恢复失败" in captured.out


def test_persist_state_os_error(tmp_path: Path):
    """测试持久化时 OSError 转换为 SystemError"""
    state_dir = tmp_path / "state"
    manager = SessionStateManager(state_dir=state_dir)

    attempt = GateAttempt(
        attempt_id="persist-uuid",
        session_id="session-1",
        task_id="task-1",
        workspace=Path("/test"),
        base_ref=None,
        changed_files=[],
        requested_at=datetime.now(timezone.utc),
        stop_reason="test",
    )
    manager.create_attempt(attempt)

    # 模拟写入失败
    with (
        patch.object(Path, "write_text", side_effect=OSError("disk full")),
        pytest.raises(SystemError, match="状态持久化失败"),
    ):
        manager._persist_state()
