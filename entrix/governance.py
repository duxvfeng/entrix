"""Governance —— fitness function 执行的策略强制。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from entrix.model import Dimension, ExecutionScope, FitnessReport, Metric, Tier

StreamOutputMode = Literal["off", "failures", "all"]


@dataclass
class GovernancePolicy:
    """控制哪些 metric 运行、何时运行，以及什么会阻塞。"""

    tier_filter: Tier | None = None
    parallel: bool = False
    max_workers: int = 4
    dry_run: bool = False
    verbose: bool = False
    stream_output: StreamOutputMode = "failures"
    min_score: float = 80.0
    fail_on_hard_gate: bool = True
    execution_scope: ExecutionScope | None = None
    dimension_filters: tuple[str, ...] = ()
    metric_filters: tuple[str, ...] = ()


def _tier_passes_filter(metric_tier: Tier, filter_tier: Tier) -> bool:
    """检查 metric 的 tier 是否处于或低于过滤级别。

    Tier 层级：fast(0) < normal(1) < deep(2)。
    --tier normal 会运行 fast 和 normal 两类 metric。
    """
    return Tier.order(metric_tier) <= Tier.order(filter_tier)


def filter_metrics(metrics: list[Metric], policy: GovernancePolicy) -> list[Metric]:
    """对 metric 列表应用 tier 过滤。"""
    result = metrics
    if policy.tier_filter is not None:
        result = [m for m in result if _tier_passes_filter(m.tier, policy.tier_filter)]
    if policy.execution_scope is not None:
        result = [m for m in result if m.execution_scope == policy.execution_scope]
    allowed_metrics = {name.strip().lower() for name in policy.metric_filters if name.strip()}
    if allowed_metrics:
        result = [m for m in result if m.name.lower() in allowed_metrics]
    return result


def filter_dimensions(
    dimensions: list[Dimension], policy: GovernancePolicy
) -> list[Dimension]:
    """对 dimension 应用 tier 过滤，只返回仍有 metric 的 dimension。"""
    result: list[Dimension] = []
    allowed_dimensions = {name.strip().lower() for name in policy.dimension_filters if name.strip()}
    for dim in dimensions:
        if allowed_dimensions and dim.name.lower() not in allowed_dimensions:
            continue
        filtered = filter_metrics(dim.metrics, policy)
        if filtered:
            result.append(
                Dimension(
                    name=dim.name,
                    weight=dim.weight,
                    threshold_pass=dim.threshold_pass,
                    threshold_warn=dim.threshold_warn,
                    metrics=filtered,
                    source_file=dim.source_file,
                )
            )
    return result


def enforce(report: FitnessReport, policy: GovernancePolicy) -> int:
    """根据 fitness 报告确定退出码。

    Returns:
        0 —— 通过
        1 —— 分数低于最低阈值
        2 —— hard gate 失败
    """
    if policy.fail_on_hard_gate and report.hard_gate_blocked:
        return 2
    if report.score_blocked:
        return 1
    return 0
