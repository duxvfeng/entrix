"""Gate Arbiter - 基于证据和策略进行裁决"""

from __future__ import annotations

from datetime import datetime, timezone

from entrix.stop_gate.model import EvidencePack, Finding, Verdict


class GateArbiter:
    """基于证据包做出最终裁决"""

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode

    def arbitrate(self, evidence: EvidencePack) -> Verdict:
        """基于证据做出裁决"""
        # 检查证据完整性
        completeness_check = self._check_evidence_completeness(evidence)
        if completeness_check != "ok":
            return self._blocked_verdict(evidence.attempt_id, completeness_check)

        # 检查硬门禁
        if evidence.fitness.get("hard_gate_blocked", False):
            return self._fail_verdict(
                evidence.attempt_id,
                "硬门禁检查失败",
                self._extract_fitness_findings(evidence),
            )

        # 检查分数门禁
        if evidence.fitness.get("score_blocked", False):
            return self._fail_verdict(
                evidence.attempt_id,
                "分数不足门禁",
                self._extract_fitness_findings(evidence),
            )

        # 检查 review trigger
        if evidence.review_trigger.get("human_review_required", False) and self.strict_mode:
            return self._blocked_verdict(
                evidence.attempt_id,
                "需要人工审查",
            )

        # 所有检查通过
        return self._pass_verdict(evidence)

    def _check_evidence_completeness(self, evidence: EvidencePack) -> str:
        """检查证据完整性"""
        if not evidence.fitness or evidence.fitness.get("status") == "unknown":
            return "缺少 fitness 证据或状态未知"

        if not evidence.review_trigger or evidence.review_trigger.get("status") == "unknown":
            return "缺少 review_trigger 证据或状态未知"

        return "ok"

    def _extract_fitness_findings(self, evidence: EvidencePack) -> list[Finding]:
        """从 fitness 证据中提取发现"""
        findings = []

        for failed_metric in evidence.fitness.get("failed_metrics", []):
            finding = Finding(
                source="fitness",
                metric=failed_metric["name"],
                severity=failed_metric.get("severity", "soft_gate"),
                message=failed_metric.get("output", "检查失败"),
                artifact_path=None,
            )
            findings.append(finding)

        return findings

    def _pass_verdict(self, evidence: EvidencePack) -> Verdict:
        """生成通过裁决"""
        return Verdict(
            attempt_id=evidence.attempt_id,
            verdict="PASS",
            decided_at=datetime.now(timezone.utc),
            reason="所有质量门禁检查通过",
            summary=f"✅ 质量门禁检查通过 - {self._get_success_summary(evidence)}",
            findings=None,
        )

    def _fail_verdict(self, attempt_id: str, reason: str, findings: list[Finding]) -> Verdict:
        """生成失败裁决"""
        return Verdict(
            attempt_id=attempt_id,
            verdict="FAIL",
            decided_at=datetime.now(timezone.utc),
            reason=reason,
            summary=f"❌ {reason}，不能结束任务",
            findings=findings,
        )

    def _blocked_verdict(self, attempt_id: str, reason: str) -> Verdict:
        """生成阻塞裁决"""
        return Verdict(
            attempt_id=attempt_id,
            verdict="BLOCKED",
            decided_at=datetime.now(timezone.utc),
            reason=reason,
            summary=f"🚫 {reason}，需要人工干预",
            findings=None,
        )

    def _get_success_summary(self, evidence: EvidencePack) -> str:
        """生成成功摘要"""
        metrics_count = evidence.fitness.get("metrics_count", 0)
        failed_count = len(evidence.fitness.get("failed_metrics", []))
        score = evidence.fitness.get("final_score", 0)

        return f"{metrics_count - failed_count}/{metrics_count} 检查通过，得分 {score}/100"
