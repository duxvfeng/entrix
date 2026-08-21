"""测试可配置的 lint 系统"""

from pathlib import Path

import pytest

from entrix.harness.lint_config import (
    create_interactive_lint_selection,
    generate_metrics_from_lint_config,
    get_enabled_lint_tools,
    load_lint_config,
    should_use_configured_lints,
)
from entrix.harness.template import _language_dimensions, profile_harness_config


class TestLintConfigSystem:
    """测试可配置 lint 系统"""

    def test_load_config(self):
        """测试配置文件加载"""
        config = load_lint_config()
        assert config is not None
        assert "languages" in config
        assert "dimension_weights" in config
        assert "defaults" in config

    def test_supported_languages(self):
        """测试支持的语言"""
        config = load_lint_config()
        languages = config.get("languages", {})

        expected_languages = ["python", "node-typescript", "java-maven", "java-gradle", "go", "rust"]
        for lang in expected_languages:
            assert lang in languages

    def test_get_enabled_python_tools(self):
        """测试获取 Python 启用的工具"""
        tools = get_enabled_lint_tools("python")
        assert len(tools) > 0
        assert all("name" in tool for tool in tools)
        assert all("command" in tool for tool in tools)

    def test_should_use_configured_lints(self):
        """测试是否应该使用配置的 lint"""
        result = should_use_configured_lints()
        assert result is True  # 我们有配置文件

    def test_generate_metrics_from_config(self):
        """测试从配置生成指标"""
        dimensions = generate_metrics_from_lint_config("python")
        assert len(dimensions) > 0

        total_weight = sum(dim["weight"] for dim in dimensions)
        assert total_weight == 100  # 权重总和应该为100

    def test_dimension_weights_config(self):
        """测试维度权重配置"""
        config = load_lint_config()
        weights = config.get("dimension_weights", {})

        total_weight = sum(weights.values())
        assert total_weight == 100

    def test_interactive_selection_prompt(self):
        """测试交互式选择提示"""
        prompt = create_interactive_lint_selection("python")
        assert "python" in prompt
        assert "选择" in prompt
        assert "ruff" in prompt.lower()

    def test_config_driven_dimensions(self):
        """测试配置驱动的维度生成"""
        dimensions = _language_dimensions("python")
        assert len(dimensions) > 0

        # 检查维度结构
        for dim in dimensions:
            assert "dimension" in dim
            assert "weight" in dim
            assert "metrics" in dim
            assert "threshold" in dim

    def test_profile_config_with_custom_lints(self):
        """测试使用自定义 lint 的项目配置"""
        config = profile_harness_config("python")

        assert "fitness" in config
        assert "dimensions" in config["fitness"]
        assert len(config["fitness"]["dimensions"]) > 0

    def test_multiple_languages_config(self):
        """测试多种语言配置"""
        for profile in ["python", "node-typescript", "go", "rust"]:
            tools = get_enabled_lint_tools(profile)
            assert isinstance(tools, list)
            assert len(tools) >= 1  # 至少应该有一个启用的工具

    def test_config_structure_validation(self):
        """测试配置结构验证"""
        config = load_lint_config()

        # 检查每个语言配置的结构
        for _lang, lang_config in config.get("languages", {}).items():
            if "code_quality" in lang_config:
                for tool in lang_config["code_quality"]:
                    required_fields = ["name", "command", "description", "tier", "enabled", "required"]
                    for field in required_fields:
                        assert field in tool


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
