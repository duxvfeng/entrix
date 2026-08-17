from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from entrix.stop_gate.collector import EvidenceCollector
from entrix.stop_gate.errors import TimeoutError
from entrix.stop_gate.model import GateAttempt


def test_collect_evidence_success():
    """测试成功收集证据"""
    dimension_score = Mock(results=[
        Mock(metric_name="pytest_pass", hard_gate=False, passed=True, output=""),
        Mock(metric_name="ruff_pass", hard_gate=False, passed=True, output=""),
    ])
    report = Mock(
        final_score=85,
        hard_gate_blocked=False,
        score_blocked=False,
        dimensions=[dimension_score],
    )

    with patch("entrix.stop_gate.collector.run_fitness_report") as mock_fitness:
        mock_fitness.return_value = (report, [Mock()])

        collector = EvidenceCollector()
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

        evidence_pack = collector.collect_evidence(attempt)

        assert evidence_pack.attempt_id == "test-uuid"
        assert evidence_pack.fitness["status"] == "pass"
        assert evidence_pack.fitness["final_score"] == 85
        assert evidence_pack.fitness["metrics_count"] == 2


def test_collect_with_review_trigger_skipped():
    """测试无规则文件时 review trigger 被跳过"""
    report = Mock(
        final_score=100,
        hard_gate_blocked=False,
        score_blocked=False,
        dimensions=[Mock(results=[])],
    )

    with patch("entrix.stop_gate.collector.run_fitness_report") as mock_fitness:
        mock_fitness.return_value = (report, [Mock()])

        collector = EvidenceCollector()
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

        evidence_pack = collector.collect_evidence(attempt)

        assert evidence_pack.review_trigger["status"] == "skipped"
        assert evidence_pack.review_trigger["reason"] == "无 Harness review 规则"


def test_collect_timeout_handling():
    """测试收集超时的处理"""
    collector = EvidenceCollector(timeout_seconds=1)

    with patch("entrix.stop_gate.collector.run_fitness_report") as mock_fitness:
        mock_fitness.side_effect = TimeoutError("fitness_check", 1)

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

        evidence_pack = collector.collect_evidence(attempt)

        assert evidence_pack.fitness["status"] == "timeout"
        assert any(
            "timeout" in str(error).lower() or "超时" in str(error)
            for error in evidence_pack.collection_errors
        )


def test_collect_fitness_error_handling():
    """测试 fitness 检查异常的处理"""
    collector = EvidenceCollector()

    with patch("entrix.stop_gate.collector.run_fitness_report") as mock_fitness:
        mock_fitness.side_effect = Exception("Fitness check failed")

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

        evidence_pack = collector.collect_evidence(attempt)

        assert evidence_pack.fitness["status"] == "error"
        assert "Fitness check failed" in evidence_pack.fitness["error"]


def test_collect_review_trigger_required(tmp_path: Path):
    """测试 review trigger 触发人工审查"""
    report = Mock(
        final_score=100,
        hard_gate_blocked=False,
        score_blocked=False,
    )
    dimension = Mock(results=[])
    trigger_mock = Mock()
    trigger_mock.name = "large_diff"
    trigger_mock.severity = "warning"
    review_report = Mock(
        human_review_required=True,
        triggers=[trigger_mock],
    )

    # 创建规则文件
    rules_file = tmp_path / "docs" / "fitness" / "review-triggers.yaml"
    rules_file.parent.mkdir(parents=True)
    rules_file.write_text("rules: []")

    with (
        patch("entrix.stop_gate.collector.run_fitness_report") as mock_fitness,
        patch("entrix.stop_gate.collector.load_harness_config") as mock_load_config,
        patch("entrix.stop_gate.collector.collect_changed_files") as mock_changed,
        patch("entrix.stop_gate.collector.collect_diff_stats") as mock_stats,
        patch("entrix.stop_gate.collector.evaluate_review_triggers") as mock_eval,
    ):
        mock_fitness.return_value = (report, [dimension])
        mock_load_config.return_value = Mock(fitness_dimensions=[], review_trigger_rules=[Mock()])
        mock_changed.return_value = ["src/main.py"]
        mock_stats.return_value = Mock(file_count=1, added_lines=10, deleted_lines=0)
        mock_eval.return_value = review_report

        collector = EvidenceCollector()
        attempt = GateAttempt(
            attempt_id="test-uuid",
            session_id="session-1",
            task_id="task-1",
            workspace=tmp_path,
            base_ref="HEAD~1",
            changed_files=["src/main.py"],
            requested_at=datetime.now(timezone.utc),
            stop_reason="test",
        )

        evidence_pack = collector.collect_evidence(attempt)

        assert evidence_pack.review_trigger["status"] == "fail"
        assert evidence_pack.review_trigger["human_review_required"] is True
        assert evidence_pack.review_trigger["triggers"][0]["name"] == "large_diff"


def test_environment_evidence_collection(tmp_path: Path):
    """测试环境证据收集"""
    import subprocess

    # 在真实临时目录中初始化 git
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "test.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    collector = EvidenceCollector()
    attempt = GateAttempt(
        attempt_id="test-uuid",
        session_id="session-1",
        task_id="task-1",
        workspace=tmp_path,
        base_ref="HEAD~1",
        changed_files=["test.py"],
        requested_at=datetime.now(timezone.utc),
        stop_reason="test",
    )

    evidence_pack = collector.collect_evidence(attempt)

    assert len(evidence_pack.revision) == 40  # git SHA
    assert evidence_pack.workspace_fingerprint != ""
    assert evidence_pack.collection_duration_seconds >= 0
