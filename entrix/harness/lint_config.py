"""读取和处理可配置的 lint 配置"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from entrix.harness.profiles import detect_profile


def load_lint_config(repo_root: Path | None = None) -> dict[str, Any]:
    """加载 lint 配置文件"""
    if repo_root is None:
        repo_root = Path.cwd()

    # 首先查找项目级别的配置
    config_paths = [
        repo_root / ".claude" / "lint-config.yaml",
        repo_root / "lint-config.yaml",
        repo_root / "skills" / "entrix" / "lint-config.yaml",
        Path(__file__).parent.parent.parent / "skills" / "entrix" / "lint-config.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    return yaml.safe_load(f)
            except Exception:
                continue

    # 返回默认空配置
    return {"languages": {}, "dimension_weights": {}, "defaults": {}}


def get_enabled_lint_tools(
    profile: str, repo_root: Path | None = None
) -> list[dict[str, Any]]:
    """获取指定语言配置文件中启用的 lint 工具"""
    config = load_lint_config(repo_root)
    languages_config = config.get("languages", {})

    if profile not in languages_config:
        return []

    language_config = languages_config[profile]
    code_quality_tools = language_config.get("code_quality", [])

    # 根据配置策略过滤启用的工具
    defaults = config.get("defaults", {})
    enable_first_only = defaults.get("enable_first_lint_only", True)

    if enable_first_only:
        # 只启用第一个工具
        enabled_tools = [tool for tool in code_quality_tools if tool.get("enabled", False)][:1]
    else:
        # 启用所有标记为 enabled 的工具
        enabled_tools = [tool for tool in code_quality_tools if tool.get("enabled", False)]

    return enabled_tools


def get_dimension_weights(repo_root: Path | None = None) -> dict[str, int]:
    """获取维度权重配置"""
    config = load_lint_config(repo_root)
    return config.get("dimension_weights", {"code_quality": 40, "testability": 35, "release_readiness": 25})


def generate_metrics_from_lint_config(
    profile: str, repo_root: Path | None = None
) -> list[dict[str, Any]]:
    """根据配置生成所有维度的 metrics"""
    config = load_lint_config(repo_root)
    languages_config = config.get("languages", {})

    if profile not in languages_config:
        return []

    language_config = languages_config[profile]
    dimension_weights = config.get("dimension_weights", {"code_quality": 40, "testability": 35, "release_readiness": 25})
    defaults = config.get("defaults", {})
    enable_first_only = defaults.get("enable_first_lint_only", True)

    all_dimensions = []

    # 为每个维度生成指标
    for dimension_name in ["code_quality", "testability", "release_readiness"]:
        if dimension_name not in language_config:
            continue

        tools = language_config[dimension_name]

        # 根据配置策略过滤启用的工具
        if enable_first_only:
            # 只启用第一个工具
            enabled_tools = [tool for tool in tools if tool.get("enabled", False)][:1]
        else:
            # 启用所有标记为 enabled 的工具
            enabled_tools = [tool for tool in tools if tool.get("enabled", False)]

        if not enabled_tools:
            continue

        # 生成指标
        metrics = []
        for tool in enabled_tools:
            metric = {
                "name": tool["name"],
                "command": tool["command"],
                "description": tool["description"],
                "tier": tool.get("tier", "normal"),
                "hard_gate": tool.get("required", False),
            }
            metrics.append(metric)

        if metrics:
            all_dimensions.append({
                "dimension": dimension_name,
                "weight": dimension_weights.get(dimension_name, 30),
                "threshold": {"pass": 100, "warn": 90},
                "metrics": metrics,
            })

    return all_dimensions


def should_use_configured_lints(repo_root: Path | None = None) -> bool:
    """检查是否应该使用配置的 lint 工具"""
    config = load_lint_config(repo_root)
    languages_config = config.get("languages", {})
    return len(languages_config) > 0


def create_interactive_lint_selection(profile: str) -> str:
    """创建交互式 lint 工具选择的提示信息"""
    config = load_lint_config()
    languages_config = config.get("languages", {})

    if profile not in languages_config:
        return f"No lint configuration found for profile: {profile}"

    language_config = languages_config[profile]
    code_quality_tools = language_config.get("code_quality", [])

    if not code_quality_tools:
        return f"No code quality tools configured for profile: {profile}"

    prompt = f"为 {profile} 项目选择 Lint 工具:\n\n"
    for idx, tool in enumerate(code_quality_tools, 1):
        status = "[X]" if tool.get("enabled", False) else "[ ]"
        required = " (必需)" if tool.get("required", False) else ""
        prompt += f"{idx}. {status} {tool['name']} - {tool['description']}{required}\n"

    prompt += "\n请输入要启用的工具编号 (多个用逗号分隔，或输入 'all' 启用所有):"
    return prompt


def update_lint_config_from_selection(profile: str, selection: str, repo_root: Path | None = None) -> bool:
    """根据用户选择更新 lint 配置"""
    if repo_root is None:
        repo_root = Path.cwd()

    config = load_lint_config(repo_root)
    languages_config = config.get("languages", {})

    if profile not in languages_config:
        return False

    language_config = languages_config[profile]
    code_quality_tools = language_config.get("code_quality", [])

    # 处理用户选择
    if selection.lower().strip() == "all":
        for tool in code_quality_tools:
            tool["enabled"] = True
    else:
        try:
            selected_indices = [int(x.strip()) - 1 for x in selection.split(",")]
            for idx in selected_indices:
                if 0 <= idx < len(code_quality_tools):
                    code_quality_tools[idx]["enabled"] = True
        except (ValueError, IndexError):
            return False

    # 保存更新后的配置
    config_path = repo_root / ".claude" / "lint-config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

    return True


def generate_profile_description_with_lints(profile: str) -> str:
    """生成包含配置的 lint 工具的项目描述"""
    enabled_tools = get_enabled_lint_tools(profile)
    dimension_weights = get_dimension_weights()

    if not enabled_tools:
        return f"Profile: {profile}, no additional lint tools configured."

    description = f"Profile: {profile}\n"
    description += f"Enabled lint tools ({len(enabled_tools)}):\n"

    for tool in enabled_tools:
        description += f"  - {tool['name']}: {tool['description']}\n"

    description += f"\nDimension weights: {dimension_weights}"
    return description
