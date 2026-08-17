import subprocess
import sys
from pathlib import Path

import pytest

from entrix.stop_gate.adapter import StopGateAdapter


@pytest.mark.integration
def test_full_stop_gate_cycle_pass(tmp_path: Path):
    """测试完整的 Stop Gate 通过循环"""
    test_repo = tmp_path / "test-repo"
    test_repo.mkdir()

    # 创建基本的项目结构
    fitness_dir = test_repo / "docs" / "fitness"
    fitness_dir.mkdir(parents=True)
    (fitness_dir / "code-quality.md").write_text("""\
---
dimension: code_quality
weight: 100
threshold:
  pass: 100
  warn: 80
metrics:
  - name: test_metric
    command: python -c "print('test passed')"
    hard_gate: false
    tier: fast
---
# Code Quality
""")

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

    # 创建会失败的质量检查
    fitness_dir = test_repo / "docs" / "fitness"
    fitness_dir.mkdir(parents=True)
    (fitness_dir / "code-quality.md").write_text(f"""\
---
dimension: code_quality
weight: 100
threshold:
  pass: 100
  warn: 80
metrics:
  - name: failing_test
    command: '{sys.executable} -c "import sys; sys.exit(1)"'
    hard_gate: true
    tier: fast
---
# Code Quality
""")

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
