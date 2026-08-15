"""进化架构 fitness function 的领域模型。

在 Entrix 中，"fitness" 沿用进化架构中的术语：一种可执行的检查，
用于衡量代码库是否仍然满足某个质量或架构目标。面向用户的文本通常将同一概念称为 guardrail。

与《Building Evolutionary Architectures》中的概念对应：
- Fitness Function → Metric（可执行的架构检查）
- Dimension → 架构特性类别
- Atomic vs Holistic → FitnessKind
- Static vs Dynamic → AnalysisMode
- Triggered vs Continuous → Tier（执行频率）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Tier(Enum):
    """执行速度层级 —— 对应触发频率。"""

    FAST = "fast"  # <30s: lints, static analysis
    NORMAL = "normal"  # <5min: unit tests, contract checks
    DEEP = "deep"  # <15min: E2E, security scans

    @staticmethod
    def order(tier: Tier) -> int:
        return {"fast": 0, "normal": 1, "deep": 2}[tier.value]


class FitnessKind(Enum):
    """Atomic 检查单一事项；holistic 检查系统级属性。"""

    ATOMIC = "atomic"
    HOLISTIC = "holistic"


class AnalysisMode(Enum):
    """Static 分析代码结构；dynamic 分析运行时行为。"""

    STATIC = "static"
    DYNAMIC = "dynamic"


class ExecutionScope(Enum):
    """metric 具有权威性的执行环境。"""

    LOCAL = "local"
    CI = "ci"
    STAGING = "staging"
    PROD_OBSERVATION = "prod_observation"


class Gate(Enum):
    """metric 结果的治理严重程度。"""

    HARD = "hard"
    SOFT = "soft"
    ADVISORY = "advisory"


class Stability(Enum):
    """面向运行时 metric 的信号稳定性分类。"""

    DETERMINISTIC = "deterministic"
    NOISY = "noisy"


class EvidenceType(Enum):
    """evidence 的收集或表示方式。"""

    COMMAND = "command"
    TEST = "test"
    PROBE = "probe"
    SARIF = "sarif"
    MANUAL_ATTESTATION = "manual_attestation"


class Confidence(Enum):
    """metric evidence 质量的置信度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ResultState(Enum):
    """Fitness V2 的扩展结果状态。"""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"
    WAIVED = "waived"


@dataclass
class Waiver:
    """临时绕过 metric 的可选豁免元数据。"""

    reason: str
    owner: str = ""
    tracking_issue: int | None = None
    expires_at: date | None = None

    def is_active(self, today: date | None = None) -> bool:
        """当 waiver 仍然有效时返回 True。"""
        reference = today or date.today()
        return self.expires_at is None or self.expires_at >= reference


@dataclass
class Metric:
    """一个可执行的 fitness function。"""

    name: str
    command: str
    pattern: str = ""
    hard_gate: bool = False
    tier: Tier = Tier.NORMAL
    description: str = ""
    kind: FitnessKind = FitnessKind.ATOMIC
    analysis: AnalysisMode = AnalysisMode.STATIC
    execution_scope: ExecutionScope = ExecutionScope.LOCAL
    gate: Gate | None = None
    stability: Stability = Stability.DETERMINISTIC
    evidence_type: EvidenceType = EvidenceType.COMMAND
    scope: list[str] = field(default_factory=list)
    run_when_changed: list[str] = field(default_factory=list)
    timeout_seconds: int | None = None
    owner: str = ""
    confidence: Confidence = Confidence.UNKNOWN
    waiver: Waiver | None = None

    def __post_init__(self) -> None:
        if self.gate is None:
            self.gate = Gate.HARD if self.hard_gate else Gate.SOFT


@dataclass
class Dimension:
    """被衡量的架构特性（例如 security、evolvability）。"""

    name: str
    weight: int  # percentage, all dimensions should sum to 100
    threshold_pass: int = 90
    threshold_warn: int = 80
    metrics: list[Metric] = field(default_factory=list)
    source_file: str = ""


@dataclass
class MetricResult:
    """执行单个 Metric 的结果。"""

    metric_name: str
    passed: bool
    output: str
    tier: Tier
    hard_gate: bool = False
    duration_ms: float = 0.0
    state: ResultState | None = None
    returncode: int | None = None

    def __post_init__(self) -> None:
        if self.state is None:
            self.state = ResultState.PASS if self.passed else ResultState.FAIL

    @property
    def is_infra_error(self) -> bool:
        """当失败很可能是基础设施/检查器问题，而非产品缺陷时返回 True。"""
        return self.state == ResultState.UNKNOWN and not self.passed


@dataclass
class DimensionScore:
    """某个 Dimension 的聚合分数。"""

    dimension: str
    weight: int
    passed: int
    total: int
    score: float  # 0-100
    hard_gate_failures: list[str] = field(default_factory=list)
    results: list[MetricResult] = field(default_factory=list)


@dataclass
class FitnessReport:
    """跨所有维度的最终报告。"""

    dimensions: list[DimensionScore] = field(default_factory=list)
    final_score: float = 0.0
    hard_gate_blocked: bool = False
    score_blocked: bool = False  # final_score < threshold
