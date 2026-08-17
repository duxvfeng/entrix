"""Harness integration with stop-gate tests."""
import io
import json
from pathlib import Path
import sys

import pytest

from entrix.stop_gate.adapter import StopGateAdapter
from entrix.stop_gate.hook import run_stop_gate_hook
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


def test_harness_runner_skips_hard_gates_when_global_when_is_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    monkeypatch.setattr(
        "entrix.harness.producers.command.CommandProducer.run",
        lambda *_args: pytest.fail("inactive Harness must not run producers"),
    )
    evidence_root = tmp_path / "runtime"

    verdict = HarnessRunner(config_path, evidence_root=evidence_root).run(
        {
            "task_id": "task-1",
            "workspace": tmp_path,
            "branch": "docs/readme-update",
        }
    )

    assert verdict.status == VerdictStatus.PASS
    assert verdict.gate_results == []
    assert "inactive" in verdict.summary
    bundle_paths = list(
        (evidence_root / ".harness" / "evidence" / "task-1").glob("*-bundle.json")
    )
    assert len(bundle_paths) == 1
    assert json.loads(bundle_paths[0].read_text(encoding="utf-8"))["active"] is False


def test_harness_runner_does_not_arbitrate_when_storage_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
evidence_producers:
  - id: tests
    type: test
    name: Tests
    command: echo passed
gate_policies:
  - name: Tests pass
    severity: hard
    rule: {evidence_id: tests, condition: 'status == "pass"'}
''',
        encoding="utf-8",
    )
    gate_called = False

    def fail_save(*_args: object) -> None:
        raise OSError("disk unavailable")

    def record_arbitration(*_args: object):
        nonlocal gate_called
        gate_called = True
        pytest.fail("GateEngine must not run without persisted evidence")

    monkeypatch.setattr("entrix.stop_gate.runner.EvidenceStore.save", fail_save)
    monkeypatch.setattr("entrix.stop_gate.runner.GateEngine.arbitrate", record_arbitration)

    with pytest.raises(OSError, match="disk unavailable"):
        HarnessRunner(config_path).run(
            {"task_id": "task-1", "workspace": tmp_path, "branch": "main"}
        )

    assert gate_called is False


def test_harness_runner_evaluates_gate_when_with_hook_context(tmp_path: Path) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
evidence_producers:
  - id: tests
    type: test
    name: Tests
    command: echo passed
gate_policies:
  - name: Frontend only
    severity: hard
    when: {changed_any: ["frontend/**"]}
    rule: {evidence_id: missing, condition: 'status == "pass"'}
  - name: Tests pass
    severity: hard
    rule: {evidence_id: tests, condition: 'status == "pass"'}
''',
        encoding="utf-8",
    )

    verdict = HarnessRunner(config_path).run(
        {
            "task_id": "task-1",
            "workspace": tmp_path,
            "changed_files": ["docs/readme.md"],
            "branch": "main",
        }
    )

    assert verdict.status == VerdictStatus.PASS
    assert verdict.gate_results[0].active is False


def test_stop_hook_recollects_evidence_after_fail_then_pass(tmp_path: Path) -> None:
    """A real hook blocks a failing report and always re-runs a later PASS."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "source.txt").write_text("1\n", encoding="utf-8")
    (workspace / "write_report.py").write_text(
        '''import json
from pathlib import Path

failed = int(Path("source.txt").read_text(encoding="utf-8").strip())
counter = Path("run-count.txt")
runs = int(counter.read_text(encoding="utf-8")) + 1 if counter.exists() else 1
counter.write_text(str(runs), encoding="utf-8")
Path("report.json").write_text(
    json.dumps({"status": "pass" if failed == 0 else "fail", "summary": {"failed": failed}}),
    encoding="utf-8",
)
''',
        encoding="utf-8",
    )
    command = f'"{sys.executable}" write_report.py'
    (workspace / "harness.yaml").write_text(
        f'''version: "harness/v1"
settings: {{failure_mode: closed}}
evidence_producers:
  - id: api-test
    type: test
    name: API tests
    command: {command!r}
    producer: fixture-report
    parser:
      type: json
      path: report.json
      status_path: status
      status_map: {{pass: pass, fail: fail}}
      summary: {{failed: summary.failed}}
gate_policies:
  - name: API tests pass
    severity: hard
    rule: {{evidence_id: api-test, condition: 'int(summary.failed) == 0'}}
''',
        encoding="utf-8",
    )
    state_dir = tmp_path / "stop-gate-state"
    payload = {"session_id": "session-1", "cwd": str(workspace)}

    def invoke() -> tuple[int, str]:
        output = io.StringIO()
        return (
            run_stop_gate_hook(
                input_stream=io.StringIO(json.dumps(payload)),
                output_stream=output,
                state_dir=state_dir,
            ),
            output.getvalue(),
        )

    first_code, first_output = invoke()

    assert first_code == 0
    assert json.loads(first_output)["decision"] == "block"
    assert (workspace / "run-count.txt").read_text(encoding="utf-8") == "1"

    (workspace / "source.txt").write_text("0\n", encoding="utf-8")
    second_code, second_output = invoke()

    assert second_code == 0
    assert second_output == ""
    assert (workspace / "run-count.txt").read_text(encoding="utf-8") == "2"

    third_code, third_output = invoke()

    assert third_code == 0
    assert third_output == ""
    assert (workspace / "run-count.txt").read_text(encoding="utf-8") == "3"
    bundles = list((state_dir / "evidence").rglob("*-bundle.json"))
    assert len(bundles) == 3
    assert json.loads(bundles[-1].read_text(encoding="utf-8"))["evidence"][0]["status"] == "pass"
