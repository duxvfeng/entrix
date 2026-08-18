"""Harness configuration loading, validation, and domain conversion."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from entrix.harness.gate.policy import GatePolicy, GateRule, Severity
from entrix.harness.gate.dsl import validate_condition_syntax
from entrix.harness.fitness import parse_dimensions
from entrix.harness.conditions import validate_when_config
from entrix.harness.evidence import EVIDENCE_STATUSES
from entrix.model import Dimension
from entrix.review_trigger import ReviewTriggerRule, parse_review_trigger_rules

SUPPORTED_VERSIONS = ("harness/v1",)
BUILTIN_PRODUCERS = frozenset({"entrix-fitness", "entrix-review-trigger", "diff-stats"})
PARSER_TYPES = frozenset(
    {"exit_code", "regex", "junit", "json", "evidence_json", "sarif"}
)
SARIF_LEVELS = frozenset({"error", "warning", "note", "none"})


@dataclass
class EvidenceProducerConfig:
    """Validated evidence producer configuration."""

    id: str = ""
    type: str = ""
    name: str = ""
    command: str | None = None
    producer: str = ""
    builtin: str | None = None
    timeout_seconds: int = 60
    when: dict[str, Any] | None = None
    parser: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, str]] = field(default_factory=list)


@dataclass
class HarnessConfig:
    """Top-level configuration consumed by the evidence and gate engines."""

    version: str = ""
    failure_mode: str = "closed"
    max_parallel_producers: int = 1
    when: dict[str, Any] | None = None
    evidence_producers: list[EvidenceProducerConfig] = field(default_factory=list)
    gate_policies: list[GatePolicy] = field(default_factory=list)
    fitness_dimensions: list[Dimension] = field(default_factory=list)
    review_trigger_rules: list[ReviewTriggerRule] = field(default_factory=list)


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是对象")
    return value


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _load_producer_configs(producers_data: Any) -> list[EvidenceProducerConfig]:
    if not isinstance(producers_data, list):
        raise ValueError("evidence_producers 必须是列表")

    producers: list[EvidenceProducerConfig] = []
    producer_ids: set[str] = set()
    for index, raw_producer in enumerate(producers_data):
        producer_data = _require_mapping(raw_producer, f"evidence_producers[{index}]")
        producer_id = _require_text(producer_data.get("id"), f"evidence_producers[{index}].id")
        if producer_id in producer_ids:
            raise ValueError(f"evidence_producers 中存在重复 id：{producer_id}")
        producer_ids.add(producer_id)

        builtin = producer_data.get("builtin")
        command = producer_data.get("command")
        if builtin is not None:
            builtin = _require_text(builtin, f"evidence_producers[{index}].builtin")
            if builtin not in BUILTIN_PRODUCERS:
                raise ValueError(f"未知 builtin producer：{builtin}")
            if command is not None:
                raise ValueError("builtin producer 不能同时配置 command")
        else:
            command = _require_text(command, f"evidence_producers[{index}].command")

        parser_data = producer_data.get("parser", {"type": "exit_code"})
        parser_data = _require_mapping(parser_data, f"evidence_producers[{index}].parser")
        parser_type = _require_text(parser_data.get("type", "exit_code"), "parser.type")
        if parser_type not in PARSER_TYPES:
            raise ValueError(f"不支持的 parser type：{parser_type}")
        parser_data = {**parser_data, "type": parser_type}
        pattern = parser_data.get("pattern")
        if parser_type == "regex" and (not isinstance(pattern, str) or not pattern):
            raise ValueError("regex parser 必须配置非空 pattern")
        if parser_type in {"junit", "json", "evidence_json", "sarif"}:
            parser_data["path"] = _require_text(
                parser_data.get("path"), f"{parser_type} parser.path"
            )
        if parser_type == "json":
            parser_data["status_path"] = _require_text(
                parser_data.get("status_path"), "json parser.status_path"
            )
            status_map = _require_mapping(
                parser_data.get("status_map"), "json parser.status_map"
            )
            for source_status, evidence_status in status_map.items():
                _require_text(source_status, "json parser.status_map key")
                if evidence_status not in EVIDENCE_STATUSES:
                    raise ValueError(
                        "json parser.status_map values must be valid Evidence statuses"
                    )
            summary = _require_mapping(parser_data.get("summary", {}), "json parser.summary")
            for field_name, source_path in summary.items():
                _require_text(field_name, "json parser.summary key")
                _require_text(source_path, f"json parser.summary.{field_name}")
        if parser_type == "sarif":
            blocking_levels = parser_data.get("blocking_levels", ["error"])
            if not isinstance(blocking_levels, list):
                raise ValueError("sarif parser.blocking_levels 必须是列表")
            if any(level not in SARIF_LEVELS for level in blocking_levels):
                raise ValueError(
                    "sarif parser.blocking_levels 只支持 error/warning/note/none"
                )
            parser_data["blocking_levels"] = list(blocking_levels)

        timeout_seconds = producer_data.get("timeout_seconds", 60)
        if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须是正整数")

        producers.append(
            EvidenceProducerConfig(
                id=producer_id,
                type=_require_text(producer_data.get("type"), f"evidence_producers[{index}].type"),
                name=_require_text(producer_data.get("name"), f"evidence_producers[{index}].name"),
                command=command,
                producer=str(producer_data.get("producer", "")),
                builtin=builtin,
                timeout_seconds=timeout_seconds,
                when=validate_when_config(
                    producer_data.get("when"), f"evidence_producers[{index}].when"
                ),
                parser={**parser_data, "type": parser_type},
                artifacts=producer_data.get("artifacts", []),
            )
        )
    return producers


def _load_gate_policies(gates_data: Any) -> list[GatePolicy]:
    if not isinstance(gates_data, list):
        raise ValueError("gate_policies 必须是列表")

    policies: list[GatePolicy] = []
    for index, raw_gate in enumerate(gates_data):
        gate_data = _require_mapping(raw_gate, f"gate_policies[{index}]")
        try:
            severity = Severity(
                _require_text(gate_data.get("severity"), f"gate_policies[{index}].severity")
            )
        except ValueError as error:
            raise ValueError(f"不支持的 severity：{gate_data.get('severity')}") from error

        rule_data = _require_mapping(gate_data.get("rule"), f"gate_policies[{index}].rule")
        evidence_id = rule_data.get("evidence_id")
        evidence_type = rule_data.get("evidence_type")
        if bool(evidence_id) == bool(evidence_type):
            if evidence_id:
                raise ValueError("gate rule 只能指定一个 evidence_id 或 evidence_type")
            raise ValueError("gate rule 必须指定 evidence_id 或 evidence_type")

        condition = _require_text(rule_data.get("condition"), "rule.condition")
        try:
            validate_condition_syntax(condition)
        except (SyntaxError, ValueError) as error:
            raise ValueError(f"无效的 gate condition：{condition}") from error

        policies.append(
            GatePolicy(
                name=_require_text(gate_data.get("name"), f"gate_policies[{index}].name"),
                severity=severity,
                when=validate_when_config(gate_data.get("when"), f"gate_policies[{index}].when"),
                rule=GateRule(
                    name=str(rule_data.get("name", "")),
                    evidence_id=_require_text(evidence_id, "rule.evidence_id") if evidence_id else None,
                    evidence_type=_require_text(evidence_type, "rule.evidence_type") if evidence_type else None,
                    condition=condition,
                    action=rule_data.get("action"),
                ),
            )
        )
    return policies


def load_harness_config(config_path: Path) -> HarnessConfig:
    """Load YAML and return a validated configuration with domain gate policies."""
    if not config_path.exists():
        raise FileNotFoundError(f"未找到 Harness 配置：{config_path}")

    data = yaml.safe_load(config_path.read_text()) or {}
    data = _require_mapping(data, "harness 配置")
    version = data.get("version", "")
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(
            f"不支持的 harness 版本：{version}。必须是以下之一：{list(SUPPORTED_VERSIONS)}"
        )

    settings = _require_mapping(data.get("settings", {}), "settings")
    failure_mode = settings.get("failure_mode", "closed")
    if failure_mode != "closed":
        raise ValueError("settings.failure_mode 仅支持 closed")
    max_parallel_producers = settings.get("max_parallel_producers", 1)
    if (
        isinstance(max_parallel_producers, bool)
        or not isinstance(max_parallel_producers, int)
        or max_parallel_producers <= 0
    ):
        raise ValueError("settings.max_parallel_producers 必须是正整数")

    producers = _load_producer_configs(data.get("evidence_producers", []))
    policies = _load_gate_policies(data.get("gate_policies", []))
    dimensions = parse_dimensions(
        _require_mapping(data.get("fitness", {}), "fitness").get("dimensions")
    )
    review_rules = parse_review_trigger_rules(
        _require_mapping(data.get("review_triggers", {}), "review_triggers").get("rules", [])
    )
    if not producers:
        raise ValueError("evidence_producers 至少需要一个 producer")
    if not policies:
        raise ValueError("gate_policies 至少需要一个 gate")

    return HarnessConfig(
        version=version,
        failure_mode=failure_mode,
        max_parallel_producers=max_parallel_producers,
        when=validate_when_config(data.get("when"), "when"),
        evidence_producers=producers,
        gate_policies=policies,
        fitness_dimensions=dimensions,
        review_trigger_rules=review_rules,
    )
