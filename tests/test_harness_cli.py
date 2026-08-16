"""Harness CLI commands tests - integrated with existing CLI framework."""
import subprocess
import tempfile
from pathlib import Path


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

        result = subprocess.run(
            ["python", "-m", "entrix.cli", "harness", "validate", str(config_path)],
            capture_output=True,
            text=True,
        )

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

        result = subprocess.run(
            ["python", "-m", "entrix.cli", "harness", "validate", str(config_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "unsupported" in output.lower() or "不支持" in output.lower() or "error" in output.lower()


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

        result = subprocess.run(
            ["python", "-m", "entrix.cli", "harness", "run", "--config", str(config_path)],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )

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
gate_policies: []
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(harness_yaml)

        result = subprocess.run(
            ["python", "-m", "entrix.cli", "harness", "run", "--config", str(config_path), "--json"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )

        assert result.returncode == 0
        # 应该是有效的 JSON
        import json

        data = json.loads(result.stdout)
        assert "task_id" in data or "status" in data