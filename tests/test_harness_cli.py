"""Harness CLI commands tests - integrated with existing CLI framework."""
import json
import subprocess
import os
import sys
import tempfile
from pathlib import Path


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    return subprocess.run(
        [sys.executable, "-m", "entrix.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd or repo_root,
        env=env,
    )


def test_harness_validate_command():
    """测试 'entrix harness validate' 命令"""
    harness_yaml = """
version: "harness/v1"

evidence_producers:
  - id: test-1
    type: test
    name: 测试
    command: pytest
    producer: pytest
    parser:
      type: exit_code

gate_policies:
  - name: 测试通过
    severity: hard
    rule:
      evidence_id: test-1
      condition: status == "pass"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(harness_yaml)

        result = _run_cli("harness", "validate", str(config_path))

        assert result.returncode == 0
        assert "valid" in result.stdout.lower() or "有效" in result.stdout.lower()


def test_harness_validate_invalid_config():
    """测试验证无效配置"""
    invalid_yaml = """
version: "harness/v2"  # 不支持的版本

evidence_producers: []
gate_policies: []
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(invalid_yaml)

        result = _run_cli("harness", "validate", str(config_path))

        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "invalid configuration" in output.lower() or "不支持" in output.lower()


def test_harness_run_command():
    """测试 'entrix harness run' 命令"""
    harness_yaml = """
version: "harness/v1"

evidence_producers:
  - id: simple-test
    type: test
    name: 简单测试
    command: echo "test output"
    producer: test
    parser:
      type: exit_code

gate_policies:
  - name: 简单测试通过
    severity: hard
    rule:
      evidence_id: simple-test
      condition: status == "pass"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(harness_yaml)

        result = _run_cli("harness", "run", "--config", str(config_path), cwd=Path(tmpdir))

        assert result.returncode == 0
        # 应该显示 PASS 状态
        assert "pass" in result.stdout.lower() or "PASS" in result.stdout


def test_harness_run_json_output():
    """测试带 JSON 输出的 'entrix harness run'"""
    harness_yaml = """
version: "harness/v1"
evidence_producers:
  - id: test-1
    type: test
    name: 测试
    command: echo "test"
    producer: test
    parser:
      type: exit_code
gate_policies:
  - name: 测试通过
    severity: hard
    rule:
      evidence_id: test-1
      condition: status == "pass"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(harness_yaml)

        result = _run_cli("harness", "run", "--config", str(config_path), "--json", cwd=Path(tmpdir))

        assert result.returncode == 0
        # 应该是有效的 JSON
        import json

        data = json.loads(result.stdout)
        assert "task_id" in data or "status" in data


def test_run_uses_inline_harness_dimensions_without_legacy_directory(tmp_path: Path):
    (tmp_path / "harness.yaml").write_text(
        '''version: "harness/v1"
fitness:
  dimensions:
    - dimension: quality
      weight: 100
      metrics:
        - name: smoke
          command: "echo ok"
          hard_gate: true
evidence_producers:
  - id: smoke-evidence
    type: test
    name: Smoke evidence
    command: "echo ok"
gate_policies:
  - name: Smoke evidence passes
    severity: hard
    rule:
      evidence_id: smoke-evidence
      condition: status == "pass"
''',
        encoding="utf-8",
    )

    result = _run_cli("run", "--min-score", "0", cwd=tmp_path)

    assert result.returncode == 0
    assert "FINAL SCORE: 100.0%" in result.stdout


def test_review_trigger_uses_inline_harness_rules(tmp_path: Path):
    (tmp_path / "harness.yaml").write_text(
        '''version: "harness/v1"
review_triggers:
  rules:
    - name: source-change
      type: changed_paths
      paths: ["src/**"]
evidence_producers:
  - id: review-evidence
    type: test
    name: Review evidence
    command: "echo ok"
gate_policies:
  - name: Review evidence passes
    severity: hard
    rule:
      evidence_id: review-evidence
      condition: status == "pass"
''',
        encoding="utf-8",
    )

    result = _run_cli("review-trigger", "--json", "src/app.py", cwd=tmp_path)

    assert result.returncode == 0
    assert json.loads(result.stdout)["triggers"][0]["name"] == "source-change"
