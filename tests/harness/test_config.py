import pytest
from pathlib import Path
from entrix.harness.config import load_harness_config, HarnessConfig


def test_load_minimal_config():
    """测试加载最小有效的 harness.yaml"""
    yaml_content = """
version: "harness/v1"

evidence_producers:
  - id: typecheck
    type: typecheck
    name: TypeScript 类型检查
    command: npm run typecheck
    producer: tsc
    parser:
      type: exit_code

gate_policies:
  - name: 类型检查通过
    severity: hard
    rule:
      evidence_id: typecheck
      condition: status == "pass"
"""
    config_path = Path("/tmp/test_harness.yaml")
    config_path.write_text(yaml_content)

    config = load_harness_config(config_path)

    assert config.version == "harness/v1"
    assert len(config.evidence_producers) == 1
    assert config.evidence_producers[0].id == "typecheck"
    assert len(config.gate_policies) == 1
    assert config.gate_policies[0].severity == "hard"


def test_load_config_with_when_conditions():
    """测试加载带有激活条件的配置"""
    yaml_content = """
version: "harness/v1"

when:
  branch:
    exclude:
      - docs/**
  env:
    CI: "true"

evidence_producers:
  - id: test
    type: test
    name: 测试
    command: pytest
    producer: pytest
    parser:
      type: exit_code
    when:
      changed_any:
        - src/**

gate_policies: []
"""
    config_path = Path("/tmp/test_harness_with_when.yaml")
    config_path.write_text(yaml_content)

    config = load_harness_config(config_path)

    assert config.when is not None
    assert config.when["branch"]["exclude"] == ["docs/**"]
    assert config.when["env"]["CI"] == "true"
    assert config.evidence_producers[0].when is not None
    assert "changed_any" in config.evidence_producers[0].when


def test_invalid_version_rejected():
    """测试不支持的架构版本被拒绝"""
    yaml_content = """
version: "harness/v2"

evidence_producers: []
gate_policies: []
"""
    config_path = Path("/tmp/test_invalid_version.yaml")
    config_path.write_text(yaml_content)

    with pytest.raises(ValueError, match="不支持的 harness 版本"):
        load_harness_config(config_path)


def test_builtin_producer():
    """测试加载内置生产者配置"""
    yaml_content = """
version: "harness/v1"

evidence_producers:
  - id: diff-stats
    type: diff
    name: Git 差异统计
    builtin: diff-stats

gate_policies: []
"""
    config_path = Path("/tmp/test_builtin.yaml")
    config_path.write_text(yaml_content)

    config = load_harness_config(config_path)

    assert config.evidence_producers[0].builtin == "diff-stats"
    assert config.evidence_producers[0].command is None


def test_regex_parser_config():
    """测试加载正则表达式解析器配置"""
    yaml_content = """
version: "harness/v1"

evidence_producers:
  - id: unit-test
    type: test
    name: 单元测试
    command: pytest
    producer: pytest
    parser:
      type: regex
      pattern: 'passed=(?P<passed>\\d+), failed=(?P<failed>\\d+)'

gate_policies: []
"""
    config_path = Path("/tmp/test_regex_parser.yaml")
    config_path.write_text(yaml_content)

    config = load_harness_config(config_path)

    assert config.evidence_producers[0].parser["type"] == "regex"
    assert "passed" in config.evidence_producers[0].parser["pattern"]
