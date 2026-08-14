from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from entrix.stop_gate.engine import StopGateEngine
from entrix.stop_gate.model import AttemptStatus, GateAttempt


def test_process_stop_request_pass():
    """测试处理成功的 stop 请求"""
    with (
        patch("entrix.stop_gate.engine.EvidenceCollector") as mock_collector,
        patch("entrix.stop_gate.engine.GateArbiter") as mock_arbiter,
        patch("entrix.stop_gate.engine.FeedbackFormatter") as mock_formatter,
    ):
        # 设置模拟返回值
        mock_evidence = Mock()
        mock_evidence.fitness = {"status": "pass", "hard_gate_blocked": False}
        mock_verdict = Mock(
            verdict="PASS",
            reason="All checks passed",
            summary="✅ All checks passed",
        )
        mock_feedback = Mock(
            user_readable="✅ Passed",
            structured={"verdict": "PASS", "block_termination": False},
            artifact_path=Path("/tmp/feedback.md"),
        )

        mock_collector.return_value.collect_evidence.return_value = mock_evidence
        mock_arbiter.return_value.arbitrate.return_value = mock_verdict
        mock_formatter.return_value.format_feedback.return_value = mock_feedback

        engine = StopGateEngine()
        attempt = GateAttempt(
            attempt_id="test-uuid",
            session_id="session-1",
            task_id="task-1",
            workspace=Path("/test"),
            base_ref="HEAD~1",
            changed_files=["src/test.py"],
            requested_at=datetime.now(timezone.utc),
            stop_reason="test",
        )

        decision = engine.process_stop_request(attempt)

        assert decision.allow_stop is True
        assert "✅" in decision.feedback
        assert decision.verdict.verdict == "PASS"


def test_process_stop_request_fail():
    """测试处理失败的 stop 请求"""
    with (
        patch("entrix.stop_gate.engine.EvidenceCollector") as mock_collector,
        patch("entrix.stop_gate.engine.GateArbiter") as mock_arbiter,
        patch("entrix.stop_gate.engine.FeedbackFormatter") as mock_formatter,
    ):
        mock_evidence = Mock()
        mock_evidence.fitness = {"status": "fail", "hard_gate_blocked": True}
        mock_verdict = Mock(
            verdict="FAIL",
            reason="Hard gate failed",
            summary="❌ Hard gate failed",
            findings=None,
        )
        mock_feedback = Mock(
            user_readable="❌ Failed",
            structured={"verdict": "FAIL", "block_termination": True},
            artifact_path=Path("/tmp/feedback.md"),
        )

        mock_collector.return_value.collect_evidence.return_value = mock_evidence
        mock_arbiter.return_value.arbitrate.return_value = mock_verdict
        mock_formatter.return_value.format_feedback.return_value = mock_feedback

        engine = StopGateEngine()
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

        decision = engine.process_stop_request(attempt)

        assert decision.allow_stop is False
        assert decision.verdict.verdict == "FAIL"


def test_process_stop_request_error_handling():
    """测试引擎错误处理"""
    with patch("entrix.stop_gate.engine.EvidenceCollector") as mock_collector:
        mock_collector.return_value.collect_evidence.side_effect = Exception("Collector failed")

        engine = StopGateEngine()
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

        decision = engine.process_stop_request(attempt)

        assert decision.allow_stop is False
        assert "错误" in decision.feedback or "ERROR" in decision.feedback
        assert decision.attempt_id == "test-uuid"


def test_get_attempt_history():
    """测试获取会话历史"""
    with (
        patch("entrix.stop_gate.engine.EvidenceCollector") as mock_collector,
        patch("entrix.stop_gate.engine.GateArbiter") as mock_arbiter,
        patch("entrix.stop_gate.engine.FeedbackFormatter") as mock_formatter,
    ):
        mock_evidence = Mock()
        mock_evidence.fitness = {"status": "pass", "hard_gate_blocked": False}
        mock_verdict = Mock(
            verdict="PASS",
            reason="All checks passed",
            summary="✅ All checks passed",
        )
        mock_feedback = Mock(
            user_readable="✅ Passed",
            structured={"verdict": "PASS", "block_termination": False},
            artifact_path=Path("/tmp/feedback.md"),
        )

        mock_collector.return_value.collect_evidence.return_value = mock_evidence
        mock_arbiter.return_value.arbitrate.return_value = mock_verdict
        mock_formatter.return_value.format_feedback.return_value = mock_feedback

        engine = StopGateEngine()
        session_id = "test-session"

        # 创建几个尝试
        for i in range(3):
            attempt = GateAttempt(
                attempt_id=f"attempt-{i}",
                session_id=session_id,
                task_id=f"task-{i}",
                workspace=Path("/test"),
                base_ref=None,
                changed_files=[],
                requested_at=datetime.now(timezone.utc),
                stop_reason="test",
            )
            engine.process_stop_request(attempt)

        history = engine.get_attempt_history(session_id)
        assert len(history) == 3


def test_verdict_to_status():
    """测试裁决转换为状态"""
    engine = StopGateEngine()
    assert engine._verdict_to_status("PASS") == AttemptStatus.PASSED
    assert engine._verdict_to_status("FAIL") == AttemptStatus.FAILED
    assert engine._verdict_to_status("BLOCKED") == AttemptStatus.BLOCKED
    assert engine._verdict_to_status("UNKNOWN") == AttemptStatus.BLOCKED


def test_engine_updates_state_manager(tmp_path: Path):
    """测试引擎更新状态管理器"""
    with (
        patch("entrix.stop_gate.engine.EvidenceCollector") as mock_collector,
        patch("entrix.stop_gate.engine.GateArbiter") as mock_arbiter,
        patch("entrix.stop_gate.engine.FeedbackFormatter") as mock_formatter,
    ):
        mock_evidence = Mock()
        mock_evidence.fitness = {"status": "pass", "hard_gate_blocked": False}
        mock_verdict = Mock(
            verdict="PASS",
            reason="All checks passed",
            summary="✅ All checks passed",
        )
        mock_feedback = Mock(
            user_readable="✅ Passed",
            structured={"verdict": "PASS", "block_termination": False},
            artifact_path=Path("/tmp/feedback.md"),
        )

        mock_collector.return_value.collect_evidence.return_value = mock_evidence
        mock_arbiter.return_value.arbitrate.return_value = mock_verdict
        mock_formatter.return_value.format_feedback.return_value = mock_feedback

        engine = StopGateEngine(state_dir=tmp_path / "state")
        attempt = GateAttempt(
            attempt_id="state-test",
            session_id="session-1",
            task_id="task-1",
            workspace=Path("/test"),
            base_ref=None,
            changed_files=[],
            requested_at=datetime.now(timezone.utc),
            stop_reason="test",
        )

        engine.process_stop_request(attempt)

        state = engine.state_manager.get_attempt("state-test")
        assert state is not None
        assert state.status == AttemptStatus.PASSED
        assert state.verdict is not None
        assert state.verdict["verdict"] == "PASS"
