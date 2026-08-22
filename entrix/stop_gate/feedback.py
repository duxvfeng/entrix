"""Stop Gate feedback formatter - 生成 Claude 可执行的结构化阻断反馈。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from entrix.harness.evidence import Evidence, EvidenceBundle
from entrix.harness.gate.arbiter import GateResult, Verdict, VerdictStatus

FEEDBACK_SCHEMA_VERSION = "stop-gate-feedback/v1"
_FEEDBACK_SECRET = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|authorization)\b\s*[:=]\s*)([^\s,;]+)"
)
_FEEDBACK_TAIL = 1200


@dataclass(frozen=True)
class BlockFeedback:
    """结构化阻断反馈，兼容 Claude Code Stop Hook 契约。"""

    decision: str
    reason: str
    status: str
    summary: str
    attempt_id: str
    evidence_bundle_path: str | None
    gates: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    collection_errors: list[dict[str, Any]]
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 输出的字典。"""
        result: dict[str, Any] = {
            "schema_version": FEEDBACK_SCHEMA_VERSION,
            "decision": self.decision,
            "reason": self.reason,
            "status": self.status,
            "summary": self.summary,
            "attempt_id": self.attempt_id,
            "evidence_bundle_path": self.evidence_bundle_path,
            "gates": self.gates,
            "evidence": self.evidence,
            "collection_errors": self.collection_errors,
            "next_action": self.next_action,
        }
        # 保留旧契约：顶层始终有 decision 和 reason
        return result


def format_block_feedback(
    verdict: Verdict,
    bundle: EvidenceBundle | None,
    *,
    bundle_path: Path | None = None,
    attempt_id: str = "",
) -> BlockFeedback:
    """把 Harness 裁决结果与证据包转换为 Claude 可执行反馈。

    Args:
        verdict: GateEngine 返回的裁决结果。
        bundle: 本次收集的证据包。
        bundle_path: 证据包持久化后的路径（可选）。
        attempt_id: 本次 Stop 尝试 ID（默认优先使用传入值，否则使用 bundle.attempt_id）。

    Returns:
        BlockFeedback 结构化反馈对象。
    """
    effective_attempt_id = attempt_id or (bundle.attempt_id if bundle is not None else "")
    status = str(getattr(verdict.status, "value", verdict.status))
    reason = verdict.summary or "Harness 门禁未通过。"

    return BlockFeedback(
        decision="block",
        reason=reason,
        status=status,
        summary=verdict.summary or reason,
        attempt_id=effective_attempt_id,
        evidence_bundle_path=str(bundle_path) if bundle_path else None,
        gates=[_gate_to_dict(gate) for gate in verdict.gate_results],
        evidence=[_evidence_to_dict(ev) for ev in (bundle.evidence if bundle is not None else [])],
        collection_errors=list(bundle.collection_errors) if bundle is not None else [],
        next_action=_next_action(status),
    )


def _next_action(status: str) -> str:
    if status == VerdictStatus.PASS.value:
        return "allow_stop"
    if status == VerdictStatus.BLOCKED.value:
        return "manual_intervention"
    return "fix_issues_and_retry"


def _gate_to_dict(gate: GateResult) -> dict[str, Any]:
    return {
        "name": gate.policy_name,
        "severity": str(gate.severity.value if hasattr(gate.severity, "value") else gate.severity),
        "active": gate.active,
        "passed": gate.passed,
        "message": gate.message,
        "matched_evidence_id": gate.matched_evidence_id,
    }


def _evidence_to_dict(evidence: Evidence) -> dict[str, Any]:
    data = asdict(evidence)
    # 只保留对 Claude 修复有用的字段，避免 raw 过大
    result = {
        "id": data.get("id"),
        "type": data.get("type"),
        "name": data.get("name"),
        "status": data.get("status"),
        "producer": data.get("producer"),
        "summary": data.get("summary") or {},
        "artifacts": [_artifact_to_dict(a) for a in data.get("artifacts", [])],
    }
    diagnostic = _diagnostic_to_dict(data.get("raw"))
    if diagnostic:
        result["diagnostic"] = diagnostic
    return result


def _diagnostic_to_dict(raw: object) -> dict[str, Any]:
    """Return a small, redacted failure tail that Claude can act on directly."""
    if not isinstance(raw, dict):
        return {}
    diagnostic: dict[str, Any] = {}
    if "exit_code" in raw:
        diagnostic["exit_code"] = raw["exit_code"]
    for field in ("stdout", "stderr"):
        value = raw.get(field)
        if not isinstance(value, str) or not value:
            continue
        sanitized = _FEEDBACK_SECRET.sub(r"\1<redacted>", value)
        diagnostic[f"{field}_tail"] = sanitized[-_FEEDBACK_TAIL:]
    return diagnostic


def _artifact_to_dict(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": artifact.get("type", ""),
        "path": artifact.get("path", ""),
    }
