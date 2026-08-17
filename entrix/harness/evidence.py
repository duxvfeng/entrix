"""证据收集系统的数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

EVIDENCE_STATUSES = frozenset({"pass", "fail", "skipped", "error", "timeout"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class Artifact:
    """证据收集产生的制品引用。"""

    type: str  # junit、sarif、log 等
    path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Evidence:
    """生产者收集的单个证据项。"""

    schema_version: str = "evidence/v1"
    id: str = ""
    type: str = ""  # test、lint、typecheck、diff、custom
    name: str = ""
    status: str = ""  # pass、fail、skipped、error、timeout
    producer: str = ""
    task_id: str = ""
    started_at: str = ""  # ISO-8601 UTC
    duration_ms: int = 0
    summary: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status and self.status not in EVIDENCE_STATUSES:
            raise ValueError(f"Unsupported evidence status: {self.status}")


@dataclass
class EvidenceBundle:
    """单次任务尝试收集的所有证据的包。"""

    schema_version: str = "evidence-bundle/v1"
    task_id: str = ""
    attempt_id: str = ""
    collected_at: str = field(default_factory=_utc_now)
    active: bool = True
    revision: str = ""
    workspace_fingerprint: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    collection_errors: list[dict[str, Any]] = field(default_factory=list)
