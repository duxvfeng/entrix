"""Gate arbiter engine tests."""
from pathlib import Path

import pytest

from entrix.harness.conditions import WhenContext
from entrix.harness.evidence import Evidence, EvidenceBundle
from entrix.harness.gate.arbiter import GateEngine, VerdictStatus
from entrix.harness.gate.policy import GatePolicy, GateRule, Severity


def test_hard_gate_pass():
    """测试通过的硬门禁"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(
                id="test-1",
                type="test",
                name="测试",
                status="pass",
                summary={"passed": 10, "failed": 0},
            )
        ],
    )

    policy = GatePolicy(
        name="测试通过",
        severity=Severity.HARD,
        rule=GateRule(name="测试规则", evidence_id="test-1", condition='status == "pass"'),
    )

    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)

    assert verdict.status == VerdictStatus.PASS
    assert len(verdict.gate_results) == 1
    assert verdict.gate_results[0].passed is True


def test_hard_gate_fail():
    """测试失败的硬门禁"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[Evidence(id="test-1", type="test", name="测试", status="fail", summary={"failed": 5})],
    )

    policy = GatePolicy(
        name="测试通过",
        severity=Severity.HARD,
        rule=GateRule(name="测试规则", evidence_id="test-1", condition='status == "pass"'),
    )

    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)

    assert verdict.status == VerdictStatus.FAIL
    assert verdict.gate_results[0].passed is False


def test_soft_gate_warning():
    """测试软门禁产生警告但通过"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[Evidence(id="test-1", type="test", name="测试", status="pass", summary={"coverage": 60})],
    )

    policy = GatePolicy(
        name="高覆盖率",
        severity=Severity.SOFT,
        rule=GateRule(name="覆盖率检查", evidence_id="test-1", condition="summary.coverage > 80"),
    )

    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)

    assert verdict.status == VerdictStatus.PASS  # 软门禁不会导致失败
    assert verdict.gate_results[0].passed is False
    assert "warning" in verdict.gate_results[0].message.lower()


def test_blocked_gate():
    """测试 blocked 门禁触发 BLOCKED 状态"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[Evidence(id="diff-1", type="diff", name="差异", summary={"added_lines": 1000})],
    )

    policy = GatePolicy(
        name="大差异",
        severity=Severity.BLOCKED,
        rule=GateRule(name="差异大小检查", evidence_id="diff-1", condition="summary.added_lines > 500"),
    )

    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)

    assert verdict.status == VerdictStatus.BLOCKED
    assert verdict.gate_results[0].passed is False


def test_evidence_type_matching():
    """测试按 evidence_type 而非 evidence_id 匹配"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="test-1", type="test", name="单元测试", status="pass"),
            Evidence(id="test-2", type="test", name="集成测试", status="pass"),
        ],
    )

    policy = GatePolicy(
        name="所有测试通过",
        severity=Severity.HARD,
        rule=GateRule(name="测试类型检查", evidence_type="test", condition='status == "pass"'),
    )

    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)

    # 应该对两个测试证据进行评估
    assert verdict.status == VerdictStatus.PASS


def test_multiple_gates():
    """测试多个门禁一起评估"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="test-1", type="test", status="pass", summary={"failed": 0}),
            Evidence(id="lint-1", type="lint", status="pass"),
        ],
    )

    policies = [
        GatePolicy(
            name="测试通过",
            severity=Severity.HARD,
            rule=GateRule(evidence_id="test-1", condition='status == "pass"'),
        ),
        GatePolicy(
            name="代码检查通过",
            severity=Severity.HARD,
            rule=GateRule(evidence_id="lint-1", condition='status == "pass"'),
        ),
    ]

    engine = GateEngine(policies)
    verdict = engine.arbitrate(bundle)

    assert verdict.status == VerdictStatus.PASS
    assert len(verdict.gate_results) == 2


def test_gate_evaluation_error():
    """测试门禁评估错误处理"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[Evidence(id="test-1", type="test", status="pass")],
    )

    policy = GatePolicy(
        name="损坏的门禁",
        severity=Severity.HARD,
        rule=GateRule(evidence_id="test-1", condition="nonexistent.field == 123"),  # 无效字段
    )

    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)

    assert verdict.status == VerdictStatus.FAIL  # 有错误的硬门禁失败
    assert "error" in verdict.gate_results[0].message.lower()


def test_hard_gate_requires_all_matching_evidence_to_pass() -> None:
    bundle = EvidenceBundle(
        evidence=[
            Evidence(id="unit", type="test", status="pass"),
            Evidence(id="integration", type="test", status="fail"),
        ]
    )
    policy = GatePolicy(
        name="All tests pass",
        severity=Severity.HARD,
        rule=GateRule(evidence_type="test", condition='status == "pass"'),
    )

    verdict = GateEngine([policy]).arbitrate(bundle, WhenContext())

    assert verdict.status == VerdictStatus.FAIL
    assert verdict.gate_results[0].passed is False


def test_blocked_gate_triggers_when_any_matching_evidence_matches() -> None:
    bundle = EvidenceBundle(
        evidence=[
            Evidence(id="clean", type="scan", status="pass"),
            Evidence(id="finding", type="scan", status="fail"),
        ]
    )
    policy = GatePolicy(
        name="No failed scan",
        severity=Severity.BLOCKED,
        rule=GateRule(evidence_type="scan", condition='status == "fail"'),
    )

    verdict = GateEngine([policy]).arbitrate(bundle, WhenContext())

    assert verdict.status == VerdictStatus.BLOCKED
    assert verdict.gate_results[0].passed is False
    assert verdict.gate_results[0].matched_evidence_id == "finding"


@pytest.mark.parametrize("severity", [Severity.HARD, Severity.BLOCKED])
def test_required_gate_without_matching_evidence_is_blocked(severity: Severity) -> None:
    policy = GatePolicy(
        name="Required evidence",
        severity=severity,
        rule=GateRule(evidence_id="missing", condition='status == "pass"'),
    )

    verdict = GateEngine([policy]).arbitrate(EvidenceBundle(), WhenContext())

    assert verdict.status == VerdictStatus.BLOCKED
    assert verdict.gate_results[0].passed is False
    assert "no matching evidence" in verdict.gate_results[0].message.lower()


def test_gate_when_marks_inactive_policy_without_affecting_verdict(
    tmp_path: Path,
) -> None:
    bundle = EvidenceBundle(evidence=[Evidence(id="tests", status="pass")])
    policies = [
        GatePolicy(
            name="Frontend tests",
            severity=Severity.HARD,
            when={"changed_any": ["frontend/**"]},
            rule=GateRule(evidence_id="missing", condition='status == "pass"'),
        ),
        GatePolicy(
            name="Tests pass",
            severity=Severity.HARD,
            rule=GateRule(evidence_id="tests", condition='status == "pass"'),
        ),
    ]
    context = WhenContext(repo_root=tmp_path, changed_files=["docs/readme.md"])

    verdict = GateEngine(policies).arbitrate(bundle, context)

    assert verdict.status == VerdictStatus.PASS
    assert verdict.gate_results[0].active is False
    assert verdict.gate_results[1].active is True


def test_zero_active_gates_is_blocked(tmp_path: Path) -> None:
    policy = GatePolicy(
        name="Frontend tests",
        severity=Severity.HARD,
        when={"changed_any": ["frontend/**"]},
        rule=GateRule(evidence_id="tests", condition='status == "pass"'),
    )
    context = WhenContext(repo_root=tmp_path, changed_files=["docs/readme.md"])

    verdict = GateEngine([policy]).arbitrate(EvidenceBundle(), context)

    assert verdict.status == VerdictStatus.BLOCKED
    assert "no active gates" in verdict.summary.lower()


def test_blocked_status_takes_priority_over_hard_failure() -> None:
    bundle = EvidenceBundle(
        evidence=[
            Evidence(id="tests", status="fail"),
            Evidence(id="scan", status="fail"),
        ]
    )
    policies = [
        GatePolicy(
            name="Tests pass",
            severity=Severity.HARD,
            rule=GateRule(evidence_id="tests", condition='status == "pass"'),
        ),
        GatePolicy(
            name="No scan finding",
            severity=Severity.BLOCKED,
            rule=GateRule(evidence_id="scan", condition='status == "fail"'),
        ),
    ]

    verdict = GateEngine(policies).arbitrate(bundle, WhenContext())

    assert verdict.status == VerdictStatus.BLOCKED
