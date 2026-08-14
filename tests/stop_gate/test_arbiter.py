from entrix.stop_gate.arbiter import GateArbiter
from entrix.stop_gate.model import EvidencePack


def test_arbitrate_pass():
    """测试通过裁决"""
    arbiter = GateArbiter()

    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={"status": "pass", "hard_gate_blocked": False, "score_blocked": False},
        review_trigger={"status": "pass", "human_review_required": False},
    )

    verdict = arbiter.arbitrate(evidence)

    assert verdict.verdict == "PASS"
    assert "通过" in verdict.summary.lower()


def test_arbitrate_fail_hard_gate():
    """测试硬门禁失败"""
    arbiter = GateArbiter()

    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={"status": "fail", "hard_gate_blocked": True, "score_blocked": False},
        review_trigger={"status": "pass", "human_review_required": False},
    )

    verdict = arbiter.arbitrate(evidence)

    assert verdict.verdict == "FAIL"
    assert "硬门禁" in verdict.reason or "失败" in verdict.reason


def test_arbitrate_fail_score_blocked():
    """测试分数门禁失败"""
    arbiter = GateArbiter()

    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={
            "status": "fail",
            "hard_gate_blocked": False,
            "score_blocked": True,
            "failed_metrics": [
                {"name": "coverage", "severity": "soft_gate", "output": "覆盖率不足"},
            ],
        },
        review_trigger={"status": "pass", "human_review_required": False},
    )

    verdict = arbiter.arbitrate(evidence)

    assert verdict.verdict == "FAIL"
    assert "分数" in verdict.reason
    assert len(verdict.findings) == 1


def test_arbitrate_blocked_missing_evidence():
    """测试证据缺失导致的阻塞"""
    arbiter = GateArbiter()

    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={},  # 缺少必需证据
        review_trigger={},
    )

    verdict = arbiter.arbitrate(evidence)

    assert verdict.verdict == "BLOCKED"
    assert "缺失" in verdict.reason or "未知" in verdict.reason


def test_arbitrate_blocked_human_review_strict_mode():
    """测试严格模式下需要人工审查导致阻塞"""
    arbiter = GateArbiter(strict_mode=True)

    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={"status": "pass", "hard_gate_blocked": False, "score_blocked": False},
        review_trigger={"status": "fail", "human_review_required": True},
    )

    verdict = arbiter.arbitrate(evidence)

    assert verdict.verdict == "BLOCKED"
    assert "人工审查" in verdict.reason


def test_arbitrate_human_review_non_strict_mode():
    """测试非严格模式下需要人工审查仍可通过"""
    arbiter = GateArbiter(strict_mode=False)

    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={"status": "pass", "hard_gate_blocked": False, "score_blocked": False},
        review_trigger={"status": "fail", "human_review_required": True},
    )

    verdict = arbiter.arbitrate(evidence)

    assert verdict.verdict == "PASS"


def test_arbitrate_extracts_findings():
    """测试从 fitness 证据中提取发现"""
    arbiter = GateArbiter()

    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={
            "status": "fail",
            "hard_gate_blocked": True,
            "score_blocked": False,
            "failed_metrics": [
                {"name": "pytest_pass", "severity": "hard_gate", "output": "测试命令退出码为 1"},
                {"name": "ruff_pass", "severity": "soft_gate", "output": "lint 错误"},
            ],
        },
        review_trigger={"status": "pass", "human_review_required": False},
    )

    verdict = arbiter.arbitrate(evidence)

    assert verdict.verdict == "FAIL"
    assert len(verdict.findings) == 2
    assert verdict.findings[0].metric == "pytest_pass"
    assert verdict.findings[0].severity == "hard_gate"


def test_arbitrate_success_summary():
    """测试通过裁决的摘要"""
    arbiter = GateArbiter()

    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={
            "status": "pass",
            "hard_gate_blocked": False,
            "score_blocked": False,
            "metrics_count": 10,
            "failed_metrics": [],
            "final_score": 85,
        },
        review_trigger={"status": "pass", "human_review_required": False},
    )

    verdict = arbiter.arbitrate(evidence)

    assert "10/10" in verdict.summary
    assert "85/100" in verdict.summary
