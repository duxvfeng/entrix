import subprocess
import sys
from pathlib import Path

import pytest

from entrix.stop_gate.adapter import StopGateAdapter


def write_harness(test_repo: Path, metric_name: str, command: str, hard_gate: bool) -> None:
    """Write a minimal Harness configuration for an integration test repository."""
    test_repo.joinpath("harness.yaml").write_text(
        f'''version: "harness/v1"
fitness:
  dimensions:
    - dimension: code_quality
      weight: 100
      threshold: {{pass: 100, warn: 80}}
      metrics:
        - name: {metric_name}
          command: {command!r}
          hard_gate: {str(hard_gate).lower()}
          tier: fast
review_triggers: {{rules: []}}
evidence_producers:
  - id: fitness
    type: fitness
    name: Entrix Fitness
    builtin: entrix-fitness
gate_policies:
  - name: Fitness must pass
    severity: hard
    rule:
      evidence_id: fitness
      condition: status == "pass"
''',
        encoding="utf-8",
    )


@pytest.mark.integration
def test_full_stop_gate_cycle_pass(tmp_path: Path):
    """测试完整的 Stop Gate 通过循环"""
    test_repo = tmp_path / "test-repo"
    test_repo.mkdir()

    write_harness(test_repo, "test_metric", "python -c \"print('test passed')\"", False)

    # 初始化 git 仓库
    subprocess.run(["git", "init"], cwd=test_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=test_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=test_repo,
        check=True,
        capture_output=True,
    )
    (test_repo / "test.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=test_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=test_repo, check=True, capture_output=True)

    # 创建适配器
    adapter = StopGateAdapter(state_dir=test_repo / ".claude" / "stop-gate")

    # 模拟 stop 请求
    session_context = {
        "session_id": "test-session",
        "task_id": "test-task",
        "workspace": test_repo,
        "changed_files": [],
        "stop_reason": "agent_completed",
    }

    decision = adapter.on_before_stop(session_context)

    # 验证结果
    assert decision.attempt_id is not None
    assert isinstance(decision.allow_stop, bool)
    assert decision.feedback is not None
    assert len(decision.feedback) > 0


@pytest.mark.integration
def test_full_stop_gate_cycle_fail(tmp_path: Path):
    """测试完整的 Stop Gate 失败循环"""
    test_repo = tmp_path / "test-repo"
    test_repo.mkdir()

    write_harness(
        test_repo,
        "failing_test",
        f'"{sys.executable}" -c "import sys; sys.exit(1)"',
        True,
    )

    # 初始化 git 仓库
    subprocess.run(["git", "init"], cwd=test_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=test_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=test_repo,
        check=True,
        capture_output=True,
    )
    (test_repo / "test.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=test_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=test_repo, check=True, capture_output=True)

    # 创建适配器
    adapter = StopGateAdapter(state_dir=test_repo / ".claude" / "stop-gate")

    session_context = {
        "session_id": "test-session",
        "task_id": "test-task",
        "workspace": test_repo,
        "changed_files": [],
        "stop_reason": "agent_completed",
    }

    decision = adapter.on_before_stop(session_context)

    # 验证失败行为
    assert decision.allow_stop is False
    assert "❌" in decision.feedback or "fail" in decision.feedback.lower()
