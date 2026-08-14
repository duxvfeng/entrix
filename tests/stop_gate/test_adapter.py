from pathlib import Path
from unittest.mock import patch

from entrix.stop_gate.adapter import StopGateAdapter
from entrix.stop_gate.model import StopDecision


def test_adapter_processes_stop_request():
    """测试适配器处理 stop 请求"""
    with patch("entrix.stop_gate.adapter.StopGateEngine") as mock_engine:
        mock_decision = StopDecision(
            allow_stop=True,
            feedback="✅ Passed",
            attempt_id="test-uuid",
        )
        mock_engine.return_value.process_stop_request.return_value = mock_decision

        adapter = StopGateAdapter()

        session_context = {
            "session_id": "session-1",
            "task_id": "task-1",
            "workspace": Path("/test"),
            "changed_files": ["src/test.py"],
            "stop_reason": "agent_completed",
        }

        decision = adapter.on_before_stop(session_context)

        assert decision.allow_stop is True
        assert decision.attempt_id == "test-uuid"


def test_adapter_handles_errors():
    """测试适配器错误处理"""
    with patch("entrix.stop_gate.adapter.StopGateEngine") as mock_engine:
        mock_engine.return_value.process_stop_request.side_effect = Exception("Test error")

        adapter = StopGateAdapter()

        session_context = {
            "session_id": "session-1",
            "task_id": "task-1",
            "workspace": Path("/test"),
            "changed_files": [],
            "stop_reason": "test",
        }

        decision = adapter.on_before_stop(session_context)

        # 错误情况下应该拒绝 stop
        assert decision.allow_stop is False
        assert "错误" in decision.feedback or "error" in decision.feedback.lower()


def test_adapter_validates_context():
    """测试适配器验证上下文"""
    adapter = StopGateAdapter()

    session_context = {
        "task_id": "task-1",
        "workspace": Path("/test"),
        "changed_files": [],
        "stop_reason": "test",
    }

    decision = adapter.on_before_stop(session_context)

    assert decision.allow_stop is False
    assert "缺少必需字段" in decision.feedback


def test_adapter_converts_string_workspace():
    """测试适配器将字符串 workspace 转换为 Path"""
    with patch("entrix.stop_gate.adapter.StopGateEngine") as mock_engine:
        mock_decision = StopDecision(
            allow_stop=True,
            feedback="✅ Passed",
            attempt_id="test-uuid",
        )
        mock_engine.return_value.process_stop_request.return_value = mock_decision

        adapter = StopGateAdapter()

        session_context = {
            "session_id": "session-1",
            "task_id": "task-1",
            "workspace": "/test",
            "changed_files": ["src/test.py"],
            "stop_reason": "agent_completed",
        }

        decision = adapter.on_before_stop(session_context)

        assert decision.allow_stop is True
        # 验证 workspace 被转换
        call_args = mock_engine.return_value.process_stop_request.call_args
        assert call_args[0][0].workspace == Path("/test")


def test_adapter_passes_base_ref():
    """测试适配器传递 base_ref"""
    with patch("entrix.stop_gate.adapter.StopGateEngine") as mock_engine:
        mock_decision = StopDecision(
            allow_stop=True,
            feedback="✅ Passed",
            attempt_id="test-uuid",
        )
        mock_engine.return_value.process_stop_request.return_value = mock_decision

        adapter = StopGateAdapter()

        session_context = {
            "session_id": "session-1",
            "task_id": "task-1",
            "workspace": Path("/test"),
            "changed_files": ["src/test.py"],
            "stop_reason": "agent_completed",
            "base_ref": "HEAD~2",
        }

        adapter.on_before_stop(session_context)

        call_args = mock_engine.return_value.process_stop_request.call_args
        assert call_args[0][0].base_ref == "HEAD~2"
