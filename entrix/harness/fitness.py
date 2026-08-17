"""Convert inline Harness fitness configuration into domain objects."""

from __future__ import annotations

from datetime import date
from typing import Any, TypeVar

from entrix.model import (
    AnalysisMode,
    Confidence,
    Dimension,
    EvidenceType,
    ExecutionScope,
    FitnessKind,
    Gate,
    Metric,
    Stability,
    Tier,
    Waiver,
)

_EnumT = TypeVar("_EnumT")


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是对象")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _string_list(value: object, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} 必须是字符串列表")
    return value


def _enum(
    raw: dict[str, Any], field_name: str, enum_type: type[_EnumT], default: _EnumT
) -> _EnumT:
    value = raw.get(field_name, default.value)
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError(f"{field_name} 不支持值：{value}") from error


def _waiver(value: object) -> Waiver | None:
    if value is None:
        return None
    raw = _mapping(value, "fitness metric.waiver")
    expires_at = raw.get("expires_at")
    if isinstance(expires_at, date):
        parsed_expiry = expires_at
    elif isinstance(expires_at, str):
        try:
            parsed_expiry = date.fromisoformat(expires_at)
        except ValueError as error:
            raise ValueError("fitness metric.waiver.expires_at 必须是 ISO 日期") from error
    elif expires_at is None:
        parsed_expiry = None
    else:
        raise ValueError("fitness metric.waiver.expires_at 必须是 ISO 日期")
    tracking_issue = raw.get("tracking_issue")
    if tracking_issue is not None and not isinstance(tracking_issue, int):
        raise ValueError("fitness metric.waiver.tracking_issue 必须是整数")
    return Waiver(
        reason=_text(raw.get("reason"), "fitness metric.waiver.reason"),
        owner=str(raw.get("owner", "")),
        tracking_issue=tracking_issue,
        expires_at=parsed_expiry,
    )


def _metric(raw_value: object, index: int, dimension_name: str) -> Metric:
    raw = _mapping(raw_value, f"fitness.dimensions[{dimension_name}].metrics[{index}]")
    hard_gate = raw.get("hard_gate", False)
    if not isinstance(hard_gate, bool):
        raise ValueError("fitness metric.hard_gate 必须是布尔值")
    timeout_seconds = raw.get("timeout_seconds")
    if timeout_seconds is not None and (
        not isinstance(timeout_seconds, int) or timeout_seconds <= 0
    ):
        raise ValueError("fitness metric.timeout_seconds 必须是正整数")
    return Metric(
        name=_text(raw.get("name"), "fitness metric.name"),
        command=_text(raw.get("command"), "fitness metric.command"),
        pattern=str(raw.get("pattern", "")),
        hard_gate=hard_gate,
        tier=_enum(raw, "tier", Tier, Tier.NORMAL),
        description=str(raw.get("description", "")),
        kind=_enum(raw, "kind", FitnessKind, FitnessKind.ATOMIC),
        analysis=_enum(raw, "analysis", AnalysisMode, AnalysisMode.STATIC),
        execution_scope=_enum(raw, "execution_scope", ExecutionScope, ExecutionScope.LOCAL),
        gate=_enum(raw, "gate", Gate, Gate.HARD if hard_gate else Gate.SOFT),
        stability=_enum(raw, "stability", Stability, Stability.DETERMINISTIC),
        evidence_type=_enum(raw, "evidence_type", EvidenceType, EvidenceType.COMMAND),
        scope=_string_list(raw.get("scope"), "fitness metric.scope"),
        run_when_changed=_string_list(
            raw.get("run_when_changed"), "fitness metric.run_when_changed"
        ),
        timeout_seconds=timeout_seconds,
        owner=str(raw.get("owner", "")),
        confidence=_enum(raw, "confidence", Confidence, Confidence.UNKNOWN),
        waiver=_waiver(raw.get("waiver")),
    )


def parse_dimensions(raw_value: object) -> list[Dimension]:
    """Parse and validate the inline ``fitness.dimensions`` list."""
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise ValueError("fitness.dimensions 必须是列表")

    dimensions: list[Dimension] = []
    names: set[str] = set()
    for index, raw_dimension in enumerate(raw_value):
        raw = _mapping(raw_dimension, f"fitness.dimensions[{index}]")
        name = _text(raw.get("dimension"), f"fitness.dimensions[{index}].dimension")
        if name in names:
            raise ValueError(f"fitness.dimensions 存在重复 dimension：{name}")
        names.add(name)
        weight = raw.get("weight")
        if not isinstance(weight, int) or weight < 0:
            raise ValueError(f"fitness.dimensions[{index}].weight 必须是非负整数")
        threshold = _mapping(raw.get("threshold", {}), f"fitness.dimensions[{index}].threshold")
        threshold_pass = threshold.get("pass", 90)
        threshold_warn = threshold.get("warn", 80)
        if not isinstance(threshold_pass, int) or not isinstance(threshold_warn, int):
            raise ValueError(f"fitness.dimensions[{index}].threshold 必须是整数")
        metrics_value = raw.get("metrics")
        if not isinstance(metrics_value, list):
            raise ValueError(f"fitness.dimensions[{index}].metrics 必须是列表")
        metrics = [_metric(metric, metric_index, name) for metric_index, metric in enumerate(metrics_value)]
        metric_names = [metric.name for metric in metrics]
        if len(metric_names) != len(set(metric_names)):
            raise ValueError(f"fitness.dimensions[{index}] 存在重复 metric name")
        dimensions.append(
            Dimension(
                name=name,
                weight=weight,
                threshold_pass=threshold_pass,
                threshold_warn=threshold_warn,
                metrics=metrics,
                source_file="harness.yaml",
            )
        )
    return dimensions


def validate_weights(dimensions: list[Dimension]) -> tuple[bool, int]:
    """Return whether configured dimension weights add up to 100."""
    total = sum(dimension.weight for dimension in dimensions)
    return total == 100, total
