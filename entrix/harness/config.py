"""Harness 配置加载和验证。"""
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional

SUPPORTED_VERSIONS = ["harness/v1"]


@dataclass
class GateRuleConfig:
    """单个门禁规则的配置。"""
    evidence_id: Optional[str] = None
    evidence_type: Optional[str] = None
    condition: str = ""
    action: Optional[str] = None


@dataclass
class GatePolicyConfig:
    """门禁策略的配置。"""
    name: str = ""
    severity: str = ""  # hard、soft、advisory、blocked
    rule: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserConfig:
    """解析命令输出的配置。"""
    type: str = ""  # exit_code、regex
    pattern: Optional[str] = None


@dataclass
class EvidenceProducerConfig:
    """证据生产者的配置。"""
    id: str = ""
    type: str = ""
    name: str = ""
    command: Optional[str] = None
    producer: str = ""
    builtin: Optional[str] = None
    timeout_seconds: int = 60
    when: Optional[Dict[str, Any]] = None
    parser: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class HarnessConfig:
    """顶层 harness 配置。"""
    version: str = ""
    when: Optional[Dict[str, Any]] = None
    evidence_producers: List[EvidenceProducerConfig] = field(default_factory=list)
    gate_policies: List[GatePolicyConfig] = field(default_factory=list)


def _load_producer_configs(producers_data: List[Dict]) -> List[EvidenceProducerConfig]:
    """从 YAML 数据加载证据生产者配置。"""
    producers = []
    for prod_data in producers_data:
        parser_data = prod_data.get("parser", {})
        parser_config = ParserConfig(
            type=parser_data.get("type", ""),
            pattern=parser_data.get("pattern")
        )

        producers.append(EvidenceProducerConfig(
            id=prod_data.get("id", ""),
            type=prod_data.get("type", ""),
            name=prod_data.get("name", ""),
            command=prod_data.get("command"),
            producer=prod_data.get("producer", ""),
            builtin=prod_data.get("builtin"),
            timeout_seconds=prod_data.get("timeout_seconds", 60),
            when=prod_data.get("when"),
            parser=parser_config.__dict__,
            artifacts=prod_data.get("artifacts", [])
        ))
    return producers


def _load_gate_policy_configs(gates_data: List[Dict]) -> List[GatePolicyConfig]:
    """从 YAML 数据加载门禁策略配置。"""
    policies = []
    for gate_data in gates_data:
        policies.append(GatePolicyConfig(
            name=gate_data.get("name", ""),
            severity=gate_data.get("severity", ""),
            rule=gate_data.get("rule", {})
        ))
    return policies


def load_harness_config(config_path: Path) -> HarnessConfig:
    """加载并验证 harness.yaml 配置。

    Args:
        config_path: harness.yaml 文件路径

    Returns:
        验证后的 HarnessConfig 对象

    Raises:
        ValueError: 如果配置无效
    """
    if not config_path.exists():
        raise FileNotFoundError(f"未找到 Harness 配置：{config_path}")

    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)

    version = data.get("version", "")
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"不支持的 harness 版本：{version}。必须是以下之一：{SUPPORTED_VERSIONS}")

    return HarnessConfig(
        version=version,
        when=data.get("when"),
        evidence_producers=_load_producer_configs(data.get("evidence_producers", [])),
        gate_policies=_load_gate_policy_configs(data.get("gate_policies", []))
    )
