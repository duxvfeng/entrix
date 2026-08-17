"""Harness integration with stop-gate tests."""
from pathlib import Path
from entrix.stop_gate.adapter import StopGateAdapter
from entrix.stop_gate.runner import HarnessRunner
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


def test_harness_runner_collects_and_arbitrates(tmp_path):
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
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(harness_yaml)
    context = {
        "task_id": "task-1",
        "workspace": tmp_path,
        "changed_files": ["src/main.py"],
        "branch": "main",
    }

    runner = HarnessRunner(config_path)
    verdict = runner.run(context)

    assert verdict.status == VerdictStatus.PASS  # 应该通过，因为 failed=0
    assert len(verdict.gate_results) == 1


def test_harness_runner_writes_evidence_outside_checked_workspace(tmp_path):
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
evidence_producers:
  - id: test-1
    type: test
    name: Test
    command: echo passed
    parser: {type: exit_code}
gate_policies:
  - name: Test passes
    severity: hard
    rule:
      evidence_id: test-1
      condition: status == "pass"
'''
    )
    evidence_root = tmp_path.parent / "stop-gate-runtime"

    verdict = HarnessRunner(config_path, evidence_root=evidence_root).run(
        {"task_id": "task-1", "workspace": tmp_path, "branch": "main"}
    )

    assert verdict.status == VerdictStatus.PASS
    assert list((evidence_root / ".harness" / "evidence" / "task-1").glob("*.json"))
    assert not (tmp_path / ".harness" / "evidence").exists()


def test_harness_runner_skips_hard_gates_when_global_when_is_inactive(tmp_path):
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
when:
  branch:
    exclude: ["docs/**"]
evidence_producers:
  - id: test-1
    type: test
    name: Test
    command: "python -c \\\"raise SystemExit(1)\\\""
    parser: {type: exit_code}
gate_policies:
  - name: Hard gate
    severity: hard
    rule:
      evidence_id: test-1
      condition: status == "pass"
'''
    )

    verdict = HarnessRunner(config_path).run(
        {
            "task_id": "task-1",
            "workspace": tmp_path,
            "branch": "docs/readme-update",
        }
    )

    assert verdict.status == VerdictStatus.PASS
    assert verdict.gate_results == []
    assert "inactive" in verdict.summary
