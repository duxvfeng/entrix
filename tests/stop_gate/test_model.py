from datetime import datetime, timezone
from pathlib import Path

from entrix.stop_gate.model import AttemptState, AttemptStatus, GateAttempt


def test_gate_attempt_creation():
    """测试 GateAttempt 基本创建"""
    attempt = GateAttempt(
        attempt_id="test-uuid-1",
        session_id="session-123",
        task_id="task-abc",
        workspace=Path("/test/workspace"),
        base_ref="HEAD~1",
        changed_files=["src/main.py"],
        requested_at=datetime.now(timezone.utc),
        stop_reason="agent_completed",
    )
    assert attempt.attempt_id == "test-uuid-1"
    assert attempt.stop_reason == "agent_completed"


def test_attempt_status_enum():
    """测试 AttemptStatus 枚举"""
    assert AttemptStatus.REQUESTED.value == "requested"
    assert AttemptStatus.COLLECTING.value == "collecting"
    assert AttemptStatus.ARBITRATING.value == "arbitrating"
    assert AttemptStatus.PASSED.value == "passed"
    assert AttemptStatus.FAILED.value == "failed"
    assert AttemptStatus.BLOCKED.value == "blocked"


def test_attempt_state_creation():
    """测试 AttemptState 创建"""
    state = AttemptState(
        attempt_id="test-uuid-1",
        status=AttemptStatus.REQUESTED,
        created_at=datetime.now(timezone.utc),
    )
    assert state.status == AttemptStatus.REQUESTED
    assert state.verdict is None
