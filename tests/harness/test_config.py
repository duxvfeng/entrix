from pathlib import Path

import pytest
from entrix.harness.config import load_harness_config
from entrix.harness.gate.policy import GatePolicy, GateRule, Severity


def test_loads_closed_settings_and_gate_when(tmp_path: Path) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
settings: {failure_mode: closed}
evidence_producers:
  - id: tests
    type: test
    name: Tests
    command: pytest
gate_policies:
  - name: Tests pass
    severity: hard
    when: {changed_any: ["src/**"]}
    rule: {evidence_id: tests, condition: 'status == "pass"'}
''',
        encoding="utf-8",
    )

    config = load_harness_config(config_path)

    assert config.failure_mode == "closed"
    assert config.gate_policies[0].when == {"changed_any": ["src/**"]}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            '''evidence_producers: []
gate_policies:
  - name: Gate
    severity: hard
    rule: {evidence_id: tests, condition: 'status == "pass"'}
''',
            "evidence_producers",
        ),
        (
            '''evidence_producers:
  - {id: tests, type: test, name: Tests, command: pytest}
gate_policies: []
''',
            "gate_policies",
        ),
        (
            '''settings: {failure_mode: open}
evidence_producers:
  - {id: tests, type: test, name: Tests, command: pytest}
gate_policies:
  - name: Gate
    severity: hard
    rule: {evidence_id: tests, condition: 'status == "pass"'}
''',
            "failure_mode",
        ),
    ],
)
def test_rejects_non_strict_or_vacuous_harness(
    tmp_path: Path, body: str, message: str
) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(f'version: "harness/v1"\n{body}', encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_harness_config(config_path)


def test_load_minimal_config(tmp_path):
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
    config_path = tmp_path / "test_harness.yaml"
    config_path.write_text(yaml_content)

    config = load_harness_config(config_path)

    assert config.version == "harness/v1"
    assert len(config.evidence_producers) == 1
    assert config.evidence_producers[0].id == "typecheck"
    assert len(config.gate_policies) == 1
    assert config.gate_policies[0].severity is Severity.HARD
    assert isinstance(config.gate_policies[0], GatePolicy)
    assert isinstance(config.gate_policies[0].rule, GateRule)
    assert config.gate_policies[0].rule.evidence_id == "typecheck"


def test_load_config_with_when_conditions(tmp_path):
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

gate_policies:
  - name: Tests pass
    severity: hard
    rule: {evidence_id: test, condition: 'status == "pass"'}
"""
    config_path = tmp_path / "test_harness_with_when.yaml"
    config_path.write_text(yaml_content)

    config = load_harness_config(config_path)

    assert config.when is not None
    assert config.when["branch"]["exclude"] == ["docs/**"]
    assert config.when["env"]["CI"] == "true"
    assert config.evidence_producers[0].when is not None
    assert "changed_any" in config.evidence_producers[0].when


def test_invalid_version_rejected(tmp_path):
    """测试不支持的架构版本被拒绝"""
    yaml_content = """
version: "harness/v2"

evidence_producers: []
gate_policies: []
"""
    config_path = tmp_path / "test_invalid_version.yaml"
    config_path.write_text(yaml_content)

    with pytest.raises(ValueError, match="不支持的 harness 版本"):
        load_harness_config(config_path)


def test_builtin_producer(tmp_path):
    """测试加载内置生产者配置"""
    yaml_content = """
version: "harness/v1"

evidence_producers:
  - id: diff-stats
    type: diff
    name: Git 差异统计
    builtin: diff-stats

gate_policies:
  - name: Diff stats available
    severity: hard
    rule: {evidence_id: diff-stats, condition: 'status == "pass"'}
"""
    config_path = tmp_path / "test_builtin.yaml"
    config_path.write_text(yaml_content)

    config = load_harness_config(config_path)

    assert config.evidence_producers[0].builtin == "diff-stats"
    assert config.evidence_producers[0].command is None


def test_regex_parser_config(tmp_path):
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

gate_policies:
  - name: Unit tests pass
    severity: hard
    rule: {evidence_id: unit-test, condition: 'status == "pass"'}
"""
    config_path = tmp_path / "test_regex_parser.yaml"
    config_path.write_text(yaml_content)

    config = load_harness_config(config_path)

    assert config.evidence_producers[0].parser["type"] == "regex"
    assert "passed" in config.evidence_producers[0].parser["pattern"]


def test_junit_parser_config(tmp_path: Path) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
evidence_producers:
  - id: tests
    type: test
    name: Tests
    command: pytest --junitxml=report.xml
    parser: {type: junit, path: report.xml}
gate_policies:
  - name: Tests pass
    severity: hard
    rule: {evidence_id: tests, condition: 'status == "pass"'}
''',
        encoding="utf-8",
    )

    config = load_harness_config(config_path)

    assert config.evidence_producers[0].parser == {"type": "junit", "path": "report.xml"}


@pytest.mark.parametrize("parser_type", ["json", "evidence_json"])
def test_json_report_parser_config(tmp_path: Path, parser_type: str) -> None:
    parser_fields = "status_path: status\n      status_map: {ok: pass}" if parser_type == "json" else ""
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        f'''version: "harness/v1"
evidence_producers:
  - id: tests
    type: test
    name: Tests
    command: run-tests
    parser:
      type: {parser_type}
      path: report.json
      {parser_fields}
gate_policies:
  - name: Tests pass
    severity: hard
    rule: {{evidence_id: tests, condition: 'status == "pass"'}}
''',
        encoding="utf-8",
    )

    config = load_harness_config(config_path)

    assert config.evidence_producers[0].parser["type"] == parser_type


@pytest.mark.parametrize(
    ("parser", "error"),
    [
        ({"type": "json", "status_path": "status", "status_map": {}}, "path"),
        ({"type": "evidence_json"}, "path"),
        ({"type": "json", "path": "report.json", "status_map": {}}, "status_path"),
        (
            {"type": "json", "path": "report.json", "status_path": "status", "status_map": []},
            "status_map",
        ),
        (
            {
                "type": "json",
                "path": "report.json",
                "status_path": "status",
                "status_map": {"ok": "unknown"},
            },
            "status_map",
        ),
        (
            {
                "type": "json",
                "path": "report.json",
                "status_path": "status",
                "status_map": {},
                "summary": [],
            },
            "summary",
        ),
    ],
)
def test_invalid_json_parser_config_is_rejected(
    tmp_path: Path, parser: dict[str, object], error: str
) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        f'''version: "harness/v1"
evidence_producers:
  - id: tests
    type: test
    name: Tests
    command: run-tests
    parser: {parser!r}
gate_policies:
  - name: Tests pass
    severity: hard
    rule: {{evidence_id: tests, condition: 'status == "pass"'}}
''',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=error):
        load_harness_config(config_path)


def test_sarif_parser_config(tmp_path: Path) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
evidence_producers:
  - id: scan
    type: security
    name: Security scan
    command: run-scan
    parser:
      type: sarif
      path: scan.sarif
      blocking_levels: [error, warning]
gate_policies:
  - name: Scan passes
    severity: hard
    rule: {evidence_id: scan, condition: 'status == "pass"'}
''',
        encoding="utf-8",
    )

    config = load_harness_config(config_path)

    assert config.evidence_producers[0].parser["blocking_levels"] == [
        "error",
        "warning",
    ]


@pytest.mark.parametrize(
    ("parser", "error"),
    [
        ({"type": "sarif"}, "path"),
        ({"type": "sarif", "path": "scan.sarif", "blocking_levels": "error"}, "blocking_levels"),
        (
            {"type": "sarif", "path": "scan.sarif", "blocking_levels": ["fatal"]},
            "blocking_levels",
        ),
    ],
)
def test_invalid_sarif_parser_config_is_rejected(
    tmp_path: Path, parser: dict[str, object], error: str
) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        f'''version: "harness/v1"
evidence_producers:
  - id: scan
    type: security
    name: Security scan
    command: run-scan
    parser: {parser!r}
gate_policies:
  - name: Scan passes
    severity: hard
    rule: {{evidence_id: scan, condition: 'status == "pass"'}}
''',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=error):
        load_harness_config(config_path)


@pytest.mark.parametrize(
    ("producer", "error"),
    [
        (
            """
  - id: duplicate
    type: test
    name: First
    command: pytest
    parser: {type: exit_code}
  - id: duplicate
    type: test
    name: Second
    command: pytest
    parser: {type: exit_code}
""",
            "重复",
        ),
        (
            """
  - id: builtin
    type: test
    name: Unknown
    builtin: missing-producer
""",
            "未知",
        ),
        (
            """
  - id: regex
    type: test
    name: Regex
    command: pytest
    parser: {type: regex}
""",
            "pattern",
        ),
    ],
)
def test_invalid_producer_config_is_rejected(tmp_path, producer, error):
    config_path = tmp_path / "invalid-producer.yaml"
    config_path.write_text(
        f'''version: "harness/v1"
evidence_producers:
{producer}
gate_policies: []
'''
    )

    with pytest.raises(ValueError, match=error):
        load_harness_config(config_path)


@pytest.mark.parametrize(
    ("rule", "error"),
    [
        ("condition: status == \"pass\"", "evidence_id 或 evidence_type"),
        (
            "evidence_id: check\n      evidence_type: test\n      condition: status == \"pass\"",
            "只能指定一个",
        ),
    ],
)
def test_gate_rule_requires_exactly_one_evidence_selector(tmp_path, rule, error):
    config_path = tmp_path / "invalid-gate.yaml"
    config_path.write_text(
        f'''version: "harness/v1"
evidence_producers: []
gate_policies:
  - name: Gate
    severity: hard
    rule:
      {rule}
'''
    )

    with pytest.raises(ValueError, match=error):
        load_harness_config(config_path)


@pytest.mark.parametrize("condition", ['status == "pass" unexpected', "status =="])
def test_invalid_gate_condition_is_rejected_during_config_load(tmp_path, condition):
    config_path = tmp_path / "invalid-condition.yaml"
    config_path.write_text(
        f'''version: "harness/v1"
evidence_producers: []
gate_policies:
  - name: Invalid condition
    severity: hard
    rule:
      evidence_id: check
      condition: {condition}
'''
    )

    with pytest.raises(ValueError, match="无效的 gate condition"):
        load_harness_config(config_path)


def test_load_harness_config_builds_inline_fitness_and_review_rules(tmp_path):
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
fitness:
  dimensions:
    - dimension: quality
      weight: 100
      metrics:
        - name: lint
          command: ruff check .
          hard_gate: true
review_triggers:
  rules:
    - name: sensitive
      type: sensitive_file_change
      paths: ["entrix/security/**"]
evidence_producers:
  - id: fitness
    type: fitness
    name: Fitness
    builtin: entrix-fitness
gate_policies:
  - name: Fitness passes
    severity: hard
    rule: {evidence_id: fitness, condition: 'status == "pass"'}
'''
    )

    config = load_harness_config(config_path)

    assert config.fitness_dimensions[0].name == "quality"
    assert config.fitness_dimensions[0].metrics[0].name == "lint"
    assert config.review_trigger_rules[0].name == "sensitive"


def test_inline_fitness_rejects_invalid_tier(tmp_path):
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
fitness:
  dimensions:
    - dimension: quality
      weight: 100
      metrics:
        - name: lint
          command: ruff check .
          tier: instant
evidence_producers: []
gate_policies: []
'''
    )

    with pytest.raises(ValueError, match="tier"):
        load_harness_config(config_path)
