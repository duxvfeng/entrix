#!/usr/bin/env python3
"""
可配置 Lint 系统使用示例

展示如何使用 Entrix 的可配置 lint 系统来自定义不同编程语言的代码质量检查。
"""

from pathlib import Path

from entrix.harness.lint_config import (
    create_interactive_lint_selection,
    get_enabled_lint_tools,
    load_lint_config,
    update_lint_config_from_selection,
)
from entrix.harness.template import profile_harness_config, render_profile_harness


def example_show_available_tools():
    """展示可用的 lint 工具"""
    print("=== 可用的 Lint 工具 ===")
    config = load_lint_config()
    languages = config.get("languages", {})

    for lang, tools in languages.items():
        print(f"\n{lang}:")
        for dimension, tool_list in tools.items():
            print(f"  {dimension}:")
            for tool in tool_list:
                status = "[X]" if tool.get("enabled", False) else "[ ]"
                print(f"    {status} {tool['name']} - {tool['description']}")


def example_enable_mypy_for_python():
    """示例：为 Python 项目启用 mypy 类型检查"""
    print("=== 为 Python 项目启用 mypy ===")

    # 示例：创建项目配置结构
    _project_config = {
        "languages": {
            "python": {
                "code_quality": [
                    {
                        "name": "mypy_check",
                        "command": "mypy . 2>&1",
                        "description": "Type checking with mypy",
                        "tier": "normal",
                        "enabled": True,  # 启用 mypy
                        "required": False
                    }
                ]
            }
        }
    }

    print("[OK] mypy 已启用")


def example_custom_rust_config():
    """示例：自定义 Rust 项目配置"""
    print("=== 自定义 Rust 项目配置 ===")

    _config = profile_harness_config('rust')
    yaml_config = render_profile_harness('rust')

    print("Rust 项目配置:")
    print(yaml_config[:500])  # 显示前500个字符


def example_interactive_selection():
    """示例：交互式选择工具"""
    print("=== 交互式工具选择 ===")
    selection_prompt = create_interactive_lint_selection('python')
    print(selection_prompt)

    # 模拟用户选择
    print("\n模拟选择: 1,2 (启用 ruff 和 mypy)")
    # update_lint_config_from_selection('python', '1,2')


def example_strict_python_config():
    """示例：严格的 Python 项目配置"""
    print("=== 严格的 Python 项目配置 ===")

    # 示例：严格模式配置结构
    _strict_config = """
    languages:
      python:
        code_quality:
          - name: ruff_lint
            enabled: true
            required: true

          - name: mypy_check
            enabled: true
            required: true

          - name: black_format_check
            enabled: true
            required: true

          - name: flake8_check
            enabled: true
            required: false
    """

    print("严格模式启用的检查:")
    print("  [X] ruff (必需)")
    print("  [X] mypy (必需)")
    print("  [X] black formatting (必需)")
    print("  [X] flake8 (可选)")


def example_vue_project_config():
    """示例：Vue 项目配置"""
    print("=== Vue 项目配置 ===")

    vue_tools = get_enabled_lint_tools('node-typescript')
    print(f"Vue/TypeScript 项目启用的工具: {len(vue_tools)} 个")

    for tool in vue_tools:
        print(f"  - {tool['name']}: {tool['description']}")


def main():
    """运行所有示例"""
    examples = [
        ("显示可用工具", example_show_available_tools),
        ("启用 mypy", example_enable_mypy_for_python),
        ("Rust 配置", example_custom_rust_config),
        ("交互式选择", example_interactive_selection),
        ("严格 Python 配置", example_strict_python_config),
        ("Vue 项目配置", example_vue_project_config),
    ]

    for name, func in examples:
        print(f"\n{'='*60}")
        print(f"示例: {name}")
        print('='*60)
        func()
        print()


if __name__ == "__main__":
    main()
