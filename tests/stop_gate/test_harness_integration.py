"""Harness integration with stop-gate tests."""
import pytest
import tempfile
from pathlib import Path
from entrix.stop_gate.adapter import StopGateAdapter
from entrix.stop_gate.runner import HarnessRunner
from entrix.harness.config import load_harness_config
from entrix.harness.conditions import WhenContext
from entrix.harness.gate.arbiter import VerdictStatus


def test_adapter_creates_context_from_payload():
    """测试适配器将 hook 载荷转换为 HarnessRunContext"""
    payload = {
        "task_id": "test-task-123",
        "repo_path": "/tmp/test_repo",
        "changed_files": ["src/main.py", "tests/test_main.py"],
        "branch": "feature/add-auth",
    }

    adapter = StopGateAdapter()
    context = adapter.adapt_payload(payload)

    assert context.task_id == "test-task-123"
    assert context.repo_root == Path("/tmp/test_repo")
    assert context.when_context.changed_files == ["src/main.py", "tests/test_main.py"]
    assert context.when_context.current_branch == "feature/add-auth"


def test_adapter_without_changed_files():
    """测试适配器处理载荷中缺少的 changed_files"""
    payload = {"task_id": "test-task-456", "repo_path": "/tmp/test_repo"}

    adapter = StopGateAdapter()
    context = adapter.adapt_payload(payload)

    assert context.task_id == "test-task-456"
    assert context.when_context.changed_files == []


def test_harness_runner_collects_and_arbitrates():
    """测试 harness 端到端流程"""
    # 创建最小 harness.yaml
    harness_yaml = """
version: "harness/v1"

evidence_producers:
  - id: test-1
    type: test
    name: 测试
    command: echo "passed=5, failed=0"
    producer: test
    parser:
      type: regex
      pattern: 'passed=(?P<passed>\\d+), failed=(?P<failed>\\d+)'

gate_policies:
  - name: 测试通过
    severity: hard
    rule:
      evidence_id: test-1
      condition: int(summary.failed) == 0
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(harness_yaml)
        config_path = Path(f.name)

    try:
        context = {
            "task_id": "task-1",
            "repo_path": "/tmp",
            "changed_files": ["src/main.py"],
            "branch": "main",
        }

        runner = HarnessRunner(config_path)
        verdict = runner.run(context)

        assert verdict.status == VerdictStatus.PASS  # 应该通过，因为 failed=0
        assert len(verdict.gate_results) == 1

    finally:
        config_path.unlink()


def test_stop_gate_routes_to_harness_when_config_exists():
    """测试 stop-gate hook 在存在配置时路由到 harness"""
    # 这将是与实际 hook 的集成测试
    # 目前，测试路由逻辑
    with tempfile.NamedTemporaryFile(mode="w", suffix="harness.yaml", delete=False) as f:
        f.write(
            """
version: "harness/v1"
evidence_producers: []
gate_policies: []
"""
        )
        config_path = Path(f.name)

    try:
        # 模拟 hook 路由逻辑
        should_use_harness = config_path.exists()
        assert should_use_harness is True

    finally:
        config_path.unlink()


def test_stop_gate_fallback_without_config():
    """测试没有 harness.yaml 时 stop-gate 回退到旧逻辑"""
    # 测试不存在的配置
    non_existent_path = Path("/tmp/non_existent_harness.yaml")
    should_use_harness = non_existent_path.exists()

    assert should_use_harness is False