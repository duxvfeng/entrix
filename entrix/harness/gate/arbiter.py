"""Gate arbitration engine."""
from dataclasses import dataclass, field
from enum import Enum
from typing import List

from entrix.harness.gate.policy import GatePolicy, Severity, GateRule
from entrix.harness.gate.dsl import evaluate_condition
from entrix.harness.evidence import EvidenceBundle, Evidence


class VerdictStatus(Enum):
    """Final arbitration status."""

    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


@dataclass
class GateResult:
    """Result of a single gate evaluation."""

    policy_name: str
    severity: Severity
    passed: bool
    message: str = ""
    matched_evidence_id: str = ""


@dataclass
class Verdict:
    """Final verdict after evaluating all gates."""

    status: VerdictStatus
    gate_results: List[GateResult] = field(default_factory=list)
    summary: str = ""


class GateEngine:
    """Engine that evaluates gate policies against evidence bundles."""

    def __init__(self, policies: List[GatePolicy]) -> None:
        """Initialize the gate engine.

        Args:
            policies: Gate policies to evaluate
        """
        self.policies = policies

    def arbitrate(self, bundle: EvidenceBundle) -> Verdict:
        """Evaluate all gate policies against the evidence bundle.

        Args:
            bundle: Evidence bundle to evaluate

        Returns:
            Verdict containing overall status and individual gate results
        """
        gate_results = []
        overall_status = VerdictStatus.PASS

        for policy in self.policies:
            result = self._evaluate_policy(policy, bundle)
            gate_results.append(result)

            # Update overall status based on severity and result
            if not result.passed:
                if policy.severity == Severity.HARD:
                    overall_status = VerdictStatus.FAIL
                elif policy.severity == Severity.BLOCKED and result.passed is False:
                    # blocked gates fail when condition is TRUE (opposite of hard)
                    overall_status = VerdictStatus.BLOCKED

        return Verdict(
            status=overall_status,
            gate_results=gate_results,
            summary=self._generate_summary(gate_results, overall_status),
        )

    def _evaluate_policy(self, policy: GatePolicy, bundle: EvidenceBundle) -> GateResult:
        """Evaluate a single policy against the evidence bundle.

        Args:
            policy: Policy to evaluate
            bundle: Evidence bundle

        Returns:
            GateResult containing evaluation results
        """
        # Ensure policy.rule is a GateRule object
        rule = policy.rule if isinstance(policy.rule, GateRule) else GateRule(**(policy.rule if isinstance(policy.rule, dict) else {}))

        # Find matching evidence
        matching_evidences = self._find_matching_evidence(rule, bundle)

        if not matching_evidences:
            return GateResult(
                policy_name=policy.name,
                severity=policy.severity,
                passed=False,
                message=f"Rule has no matching evidence: {policy.rule.evidence_id or policy.rule.evidence_type}",
            )

        # Evaluate all matching evidences
        all_passed = True
        messages = []

        for evidence in matching_evidences:
            try:
                condition_result = evaluate_condition(policy.rule.condition, evidence)
                if not condition_result:
                    all_passed = False
                    if policy.severity == Severity.SOFT:
                        messages.append(f"Warning: condition not met for evidence {evidence.id}")
                    else:
                        messages.append(f"Failed for evidence {evidence.id}")
            except Exception as e:
                all_passed = False
                error_msg = str(e).lower()
                # Check if it's a field access error
                if "none" in error_msg or "field" in error_msg or "attribute" in error_msg:
                    messages.append(f"Error: condition references invalid field")
                else:
                    messages.append(f"Error evaluating condition: {str(e)}")

        message = "; ".join(messages) if messages else "Passed"

        # For blocked gates, logic is inverted - condition TRUE means failure
        if policy.severity == Severity.BLOCKED:
            all_passed = not all_passed

        return GateResult(
            policy_name=policy.name,
            severity=policy.severity,
            passed=all_passed,
            message=message,
            matched_evidence_id=matching_evidences[0].id if matching_evidences else "",
        )

    def _find_matching_evidence(self, rule, bundle: EvidenceBundle) -> List[Evidence]:
        """Find evidence that matches the rule.

        Args:
            rule: Gate rule with evidence_id or evidence_type
            bundle: Evidence bundle to search

        Returns:
            List of matching evidence items
        """
        if rule.evidence_id:
            # Match by specific ID
            for evidence in bundle.evidence:
                if evidence.id == rule.evidence_id:
                    return [evidence]
            return []

        if rule.evidence_type:
            # Match by type
            return [ev for ev in bundle.evidence if ev.type == rule.evidence_type]

        return []

    def _generate_summary(self, gate_results: List[GateResult], status: VerdictStatus) -> str:
        """Generate human-readable summary.

        Args:
            gate_results: Individual gate results
            status: Overall verdict status

        Returns:
            Summary string
        """
        passed_count = sum(1 for r in gate_results if r.passed)
        total_count = len(gate_results)

        if status == VerdictStatus.PASS:
            return f"All gates passed ({passed_count}/{total_count})"
        elif status == VerdictStatus.FAIL:
            failed_gates = [r.policy_name for r in gate_results if not r.passed and r.severity == Severity.HARD]
            return f"Hard gates failed: {', '.join(failed_gates)}"
        elif status == VerdictStatus.BLOCKED:
            blocked_gates = [r.policy_name for r in gate_results if not r.passed and r.severity == Severity.BLOCKED]
            return f"Blocked gates triggered: {', '.join(blocked_gates)}"

        return "Unknown status"