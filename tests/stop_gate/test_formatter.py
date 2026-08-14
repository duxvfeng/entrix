from datetime import datetime, timezone
from pathlib import Path

from entrix.stop_gate.formatter import FeedbackFormatter
from entrix.stop_gate.model import Finding, Verdict


def test_format_pass_feedback(tmp_path: Path):
    """测试格式化通过反馈"""
    formatter = FeedbackFormatter(output_dir=tmp_path / "feedback")

    verdict = Verdict(
        attempt_id="test-uuid",
        verdict="PASS",
        decided_at=datetime.now(timezone.utc),
        reason="所有检查通过",
        summary="✅ 12/12 检查通过，得分 85/100",
    )

    feedback = formatter.format_feedback(verdict)

    assert feedback.user_readable.startswith("✅")
    assert "通过" in feedback.user_readable
    assert feedback.structured["verdict"] == "PASS"
    assert feedback.structured["block_termination"] is False
    assert feedback.artifact_path is not None
    assert feedback.artifact_path.exists()


def test_format_fail_feedback(tmp_path: Path):
    """测试格式化失败反馈"""
    formatter = FeedbackFormatter(output_dir=tmp_path / "feedback")

    verdict = Verdict(
        attempt_id="test-uuid",
        verdict="FAIL",
        decided_at=datetime.now(timezone.utc),
        reason="2 个质量门禁未通过",
        summary="❌ 2 个质量门禁未通过",
        findings=[
            Finding(
                source="fitness",
                metric="pytest_pass",
                severity="hard_gate",
                message="测试命令退出码为 1",
            ),
        ],
    )

    feedback = formatter.format_feedback(verdict)

    assert "❌" in feedback.user_readable
    assert "pytest_pass" in feedback.user_readable
    assert feedback.structured["block_termination"] is True
    assert "next_action" in feedback.structured
    assert feedback.structured["next_action"] == "fix_issues_and_retry"
    assert "findings" in feedback.structured


def test_format_blocked_feedback(tmp_path: Path):
    """测试格式化阻塞反馈"""
    formatter = FeedbackFormatter(output_dir=tmp_path / "feedback")

    verdict = Verdict(
        attempt_id="test-uuid",
        verdict="BLOCKED",
        decided_at=datetime.now(timezone.utc),
        reason="需要人工审查",
        summary="🚫 需要人工审查",
    )

    feedback = formatter.format_feedback(verdict)

    assert "🚫" in feedback.user_readable
    assert feedback.structured["verdict"] == "BLOCKED"
    assert feedback.structured["next_action"] == "manual_intervention"


def test_artifact_files_created(tmp_path: Path):
    """测试 artifact 文件被正确创建"""
    formatter = FeedbackFormatter(output_dir=tmp_path / "feedback")

    verdict = Verdict(
        attempt_id="artifact-test",
        verdict="PASS",
        decided_at=datetime.now(timezone.utc),
        reason="所有检查通过",
        summary="✅ 检查通过",
    )

    feedback = formatter.format_feedback(verdict)

    md_file = tmp_path / "feedback" / "artifact-test.md"
    json_file = tmp_path / "feedback" / "artifact-test.json"

    assert md_file.exists()
    assert json_file.exists()
    assert feedback.artifact_path == md_file

    # 验证 JSON 内容
    import json

    structured = json.loads(json_file.read_text(encoding="utf-8"))
    assert structured["verdict"] == "PASS"
    assert structured["attempt_id"] == "artifact-test"


def test_default_output_dir():
    """测试默认输出目录"""
    formatter = FeedbackFormatter()
    assert formatter.output_dir == Path.cwd() / ".claude" / "stop-gate" / "feedback"


def test_findings_in_structured_feedback(tmp_path: Path):
    """测试结构化反馈中包含 findings"""
    formatter = FeedbackFormatter(output_dir=tmp_path / "feedback")

    verdict = Verdict(
        attempt_id="test-uuid",
        verdict="FAIL",
        decided_at=datetime.now(timezone.utc),
        reason="检查失败",
        summary="❌ 检查失败",
        findings=[
            Finding(
                source="fitness",
                metric="ruff",
                severity="soft_gate",
                message="lint 失败",
                suggestions=["运行 ruff check --fix"],
            ),
        ],
    )

    feedback = formatter.format_feedback(verdict)

    assert len(feedback.structured["findings"]) == 1
    assert feedback.structured["findings"][0]["metric"] == "ruff"
    assert feedback.structured["findings"][0]["suggestions"] == ["运行 ruff check --fix"]
