"""核心数据模型定义"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


class AttemptStatus(Enum):
    """Stop 尝试的状态"""

    REQUESTED = "requested"
    COLLECTING = "collecting"
    ARBITRATING = "arbitrating"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass
class GateAttempt:
    """Stop 请求的完整上下文"""

    attempt_id: str
    session_id: str
    task_id: str
    workspace: Path
    base_ref: str | None
    changed_files: list[str]
    requested_at: datetime
    stop_reason: str

    @classmethod
    def create(
        cls,
        session_id: str,
        task_id: str,
        workspace: Path,
        changed_files: list[str],
        stop_reason: str,
        base_ref: str | None = None,
    ) -> GateAttempt:
        """创建新的 GateAttempt，自动生成 attempt_id"""
        return cls(
            attempt_id=str(uuid4()),
            session_id=session_id,
            task_id=task_id,
            workspace=workspace,
            base_ref=base_ref,
            changed_files=changed_files,
            requested_at=datetime.now(timezone.utc),
            stop_reason=stop_reason,
        )


@dataclass
class AttemptState:
    """尝试的运行时状态"""

    attempt_id: str
    status: AttemptStatus
    created_at: datetime
    updated_at: datetime | None = None
    attempt_data: GateAttempt | None = None
    verdict: Verdict | None = None
    evidence_pack_path: Path | None = None


@dataclass
class Finding:
    """具体的检查发现"""

    source: str
    metric: str
    severity: Literal["hard_gate", "soft_gate", "advisory"]
    message: str
    artifact_path: str | None = None
    suggestions: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    """最终裁决"""

    attempt_id: str
    verdict: Literal["PASS", "FAIL", "BLOCKED"]
    decided_at: datetime
    reason: str
    summary: str
    findings: list[Finding] | None = None


@dataclass
class EvidencePack:
    """证据集合"""

    schema_version: str = "evidence-pack.v1"
    attempt_id: str = ""
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    revision: str = ""
    workspace_fingerprint: str = ""
    fitness: dict[str, Any] = field(default_factory=dict)
    review_trigger: dict[str, Any] = field(default_factory=dict)
    collection_errors: list[dict[str, Any]] = field(default_factory=list)
    collection_duration_seconds: float = 0.0


@dataclass
class StopDecision:
    """Stop 决策结果"""

    allow_stop: bool
    feedback: str
    attempt_id: str
    verdict: Verdict | None = None
