"""证据收集系统的数据模型。"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class Artifact:
    """证据收集产生的制品引用。"""
    type: str  # junit、sarif、log 等
    path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


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
    summary: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Artifact] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceBundle:
    """单次任务尝试收集的所有证据的包。"""
    schema_version: str = "evidence-bundle/v1"
    task_id: str = ""
    attempt_id: str = ""
    collected_at: str = ""
    evidence: List[Evidence] = field(default_factory=list)
    collection_errors: List[Dict[str, Any]] = field(default_factory=list)
