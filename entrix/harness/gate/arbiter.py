"""Gate arbitration engine."""
from dataclasses import dataclass, field
from enum import Enum
from typing import List

from entrix.harness.conditions import WhenContext, evaluate_when
from entrix.harness.evidence import Evidence, EvidenceBundle
from entrix.harness.gate.dsl import evaluate_condition
from entrix.harness.gate.policy import GatePolicy, Severity


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
    active: bool = True
    missing_evidence: bool = False


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

    def arbitrate(
        self, bundle: EvidenceBundle, when_context: WhenContext | None = None
    ) -> Verdict:
        """Evaluate all gate policies against the evidence bundle.

        Args:
            bundle: Evidence bundle to evaluate

        Returns:
            Verdict containing overall status and individual gate results
        """
        if not bundle.active:
            return Verdict(
                status=VerdictStatus.PASS,
                summary="Harness inactive for current context",
            )

        context = when_context or WhenContext()
        gate_results: list[GateResult] = []
        overall_status = VerdictStatus.PASS
        active_count = 0

        for policy in self.policies:
            if not evaluate_when(policy.when, context):
                gate_results.append(
                    GateResult(
                        policy_name=policy.name,
                        severity=policy.severity,
                        passed=True,
                        active=False,
                        message="Gate when condition not met",
                    )
                )
                continue

            active_count += 1
            result = self._evaluate_policy(policy, bundle)
            gate_results.append(result)

            if result.missing_evidence and policy.severity in {
                Severity.HARD,
                Severity.BLOCKED,
            }:
                overall_status = VerdictStatus.BLOCKED
            elif not result.passed:
                if policy.severity == Severity.HARD and overall_status != VerdictStatus.BLOCKED:
                    overall_status = VerdictStatus.FAIL
                elif policy.severity == Severity.BLOCKED:
                    overall_status = VerdictStatus.BLOCKED

        if active_count == 0:
            return Verdict(
                status=VerdictStatus.BLOCKED,
                gate_results=gate_results,
                summary="No active gates for an active Harness",
            )

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
        rule = policy.rule

        # Find matching evidence
        matching_evidences = self._find_matching_evidence(rule, bundle)

        if not matching_evidences:
            return GateResult(
                policy_name=policy.name,
                severity=policy.severity,
                passed=False,
                message=f"Rule has no matching evidence: {rule.evidence_id or rule.evidence_type}",
                missing_evidence=True,
            )

        matched_id = matching_evidences[0].id
        failures: list[str] = []
        triggers: list[str] = []
        errors: list[str] = []

        for evidence in matching_evidences:
            try:
                condition_result = evaluate_condition(rule.condition, evidence)
                if policy.severity == Severity.BLOCKED:
                    if condition_result:
                        triggers.append(evidence.id)
                elif not condition_result:
                    failures.append(evidence.id)
            except Exception as error:  # noqa: BLE001
                error_msg = str(error).lower()
                # Check if it's a field access error
                if "none" in error_msg or "field" in error_msg or "attribute" in error_msg:
                    errors.append("Error: condition references invalid field")
                else:
                    errors.append(f"Error evaluating condition: {error}")

        if policy.severity == Severity.BLOCKED:
            passed = not triggers and not errors
            if triggers:
                matched_id = triggers[0]
                messages = [f"Blocked by evidence {evidence_id}" for evidence_id in triggers]
            else:
                messages = []
            messages.extend(errors)
            message = "; ".join(messages) if messages else "Not triggered"
        else:
            passed = not failures and not errors
            if failures:
                matched_id = failures[0]
            prefix = "Warning" if policy.severity == Severity.SOFT else "Failed"
            messages = [f"{prefix} for evidence {evidence_id}" for evidence_id in failures]
            messages.extend(errors)
            message = "; ".join(messages) if messages else "Passed"

        return GateResult(
            policy_name=policy.name,
            severity=policy.severity,
            passed=passed,
            message=message,
            matched_evidence_id=matched_id,
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
        active_results = [result for result in gate_results if result.active]
        passed_count = sum(1 for result in active_results if result.passed)
        total_count = len(active_results)

        if status == VerdictStatus.PASS:
            return f"All gates passed ({passed_count}/{total_count})"
        elif status == VerdictStatus.FAIL:
            failed_gates = [r.policy_name for r in gate_results if not r.passed and r.severity == Severity.HARD]
            return f"Hard gates failed: {', '.join(failed_gates)}"
        elif status == VerdictStatus.BLOCKED:
            blocked_gates = [
                result.policy_name
                for result in active_results
                if not result.passed
                and (result.severity == Severity.BLOCKED or result.missing_evidence)
            ]
            return f"Blocked gates triggered: {', '.join(blocked_gates)}"

        return "Unknown status"
