from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from entrix.stop_gate.model import (
    AttemptState,
    AttemptStatus,
    EvidencePack,
    Finding,
    GateAttempt,
    StopDecision,
    Verdict,
)


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


def test_gate_attempt_create():
    """测试 GateAttempt.create 工厂方法"""
    workspace = Path("/test/workspace")
    attempt = GateAttempt.create(
        session_id="session-123",
        task_id="task-abc",
        workspace=workspace,
        changed_files=["src/main.py"],
        stop_reason="agent_completed",
    )

    # attempt_id 是有效的 UUID
    assert UUID(attempt.attempt_id)
    assert attempt.session_id == "session-123"
    assert attempt.task_id == "task-abc"
    assert attempt.workspace == workspace
    assert attempt.changed_files == ["src/main.py"]
    assert attempt.stop_reason == "agent_completed"
    assert attempt.base_ref is None
    assert attempt.requested_at.tzinfo == timezone.utc


def test_gate_attempt_create_with_base_ref():
    """测试 GateAttempt.create 可传递 base_ref"""
    attempt = GateAttempt.create(
        session_id="session-123",
        task_id="task-abc",
        workspace=Path("/test/workspace"),
        changed_files=["src/main.py"],
        stop_reason="agent_completed",
        base_ref="HEAD~1",
    )
    assert attempt.base_ref == "HEAD~1"


def test_attempt_status_enum():
    """测试 AttemptStatus 枚举"""
    assert AttemptStatus.REQUESTED.value == "requested"
    assert AttemptStatus.COLLECTING.value == "collecting"
    assert AttemptStatus.ARBITRATING.value == "arbitrating"
    assert AttemptStatus.PASSED.value == "passed"
    assert AttemptStatus.FAILED.value == "failed"
    assert AttemptStatus.BLOCKED.value == "blocked"
    assert AttemptStatus.TIMEOUT.value == "timeout"


def test_attempt_state_creation():
    """测试 AttemptState 创建"""
    state = AttemptState(
        attempt_id="test-uuid-1",
        status=AttemptStatus.REQUESTED,
        created_at=datetime.now(timezone.utc),
    )
    assert state.status == AttemptStatus.REQUESTED
    assert state.verdict is None
    assert state.updated_at is None
    assert state.attempt_data is None
    assert state.evidence_pack_path is None


def test_finding_creation():
    """测试 Finding 创建和默认值"""
    finding = Finding(
        source="fitness",
        metric="pytest_pass",
        severity="hard_gate",
        message="测试命令退出码为 1",
    )
    assert finding.source == "fitness"
    assert finding.metric == "pytest_pass"
    assert finding.severity == "hard_gate"
    assert finding.message == "测试命令退出码为 1"
    assert finding.artifact_path is None
    assert finding.suggestions == []


def test_verdict_creation():
    """测试 Verdict 创建"""
    now = datetime.now(timezone.utc)
    verdict = Verdict(
        attempt_id="test-uuid",
        verdict="PASS",
        decided_at=now,
        reason="所有检查通过",
        summary="✅ 检查通过",
    )
    assert verdict.attempt_id == "test-uuid"
    assert verdict.verdict == "PASS"
    assert verdict.decided_at == now
    assert verdict.reason == "所有检查通过"
    assert verdict.summary == "✅ 检查通过"
    assert verdict.findings is None


def test_evidence_pack_defaults():
    """测试 EvidencePack 默认值"""
    pack = EvidencePack()
    assert pack.schema_version == "evidence-pack.v1"
    assert pack.attempt_id == ""
    assert pack.revision == ""
    assert pack.workspace_fingerprint == ""
    assert pack.fitness == {}
    assert pack.review_trigger == {}
    assert pack.collection_errors == []
    assert pack.collection_duration_seconds == 0.0
    assert pack.collected_at.tzinfo == timezone.utc


def test_stop_decision_creation():
    """测试 StopDecision 创建"""
    decision = StopDecision(
        allow_stop=True,
        feedback="✅ 检查通过",
        attempt_id="test-uuid",
    )
    assert decision.allow_stop is True
    assert decision.feedback == "✅ 检查通过"
    assert decision.attempt_id == "test-uuid"
    assert decision.verdict is None
