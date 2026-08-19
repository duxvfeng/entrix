"""测试代码变更检测逻辑 - 只有代码变更才触发 Stop Gate"""

from entrix.stop_gate.hook import has_code_change


def test_only_documentation():
    """只修改文档文件 - 不触发"""
    changed = ["docs/README.md", "docs/api.md", "CHANGELOG.md"]
    assert not has_code_change(changed)
    print("✅ 只修改文档 -> 不触发检查")


def test_only_readme():
    """只修改 README - 不触发"""
    changed = ["README.md"]
    assert not has_code_change(changed)
    print("✅ 只修改 README -> 不触发检查")


def test_code_change():
    """修改了源代码 - 触发"""
    changed = ["src/main.py", "docs/README.md"]
    assert has_code_change(changed)
    print("✅ 修改源代码 -> 触发检查")


def test_config_change():
    """修改了配置文件 - 触发"""
    changed = ["docs/guide.md", "pyproject.toml"]
    assert has_code_change(changed)
    print("✅ 修改配置文件 -> 触发检查")


def test_test_change():
    """修改了测试文件 - 触发"""
    changed = ["docs/test.md", "tests/test_main.py"]
    assert has_code_change(changed)
    print("✅ 修改测试文件 -> 触发检查")


def test_no_change():
    """没有变更 - 不触发"""
    changed = []
    assert not has_code_change(changed)
    print("✅ 没有变更 -> 不触发检查")


def test_mixed_doc_only():
    """混合文档类型 - 不触发"""
    changed = ["docs/guide.md", "README.md", "CHANGELOG.md", "docs/api.md"]
    assert not has_code_change(changed)
    print("✅ 混合文档 -> 不触发检查")


def test_markdown_in_docs():
    """docs 目录下的 markdown - 不触发"""
    changed = ["docs/design.md"]
    assert not has_code_change(changed)
    print("✅ docs/design.md -> 不触发检查")


def test_python_change():
    """修改 Python 文件 - 触发"""
    changed = ["entrix/cli.py"]
    assert has_code_change(changed)
    print("✅ 修改 .py 文件 -> 触发检查")


def test_github_workflow():
    """修改 GitHub Actions - 触发"""
    changed = [".github/workflows/test.yml"]
    assert has_code_change(changed)
    print("✅ 修改 .github -> 触发检查")


def test_yaml_change():
    """修改 YAML 文件 - 触发"""
    changed = ["harness.yaml"]
    assert has_code_change(changed)
    print("✅ 修改 .yaml -> 触发检查")


def test_shell_script():
    """修改 Shell 脚本 - 触发"""
    changed = ["scripts/deploy.sh"]
    assert has_code_change(changed)
    print("✅ 修改 .sh -> 触发检查")


if __name__ == "__main__":
    print("🧪 测试代码变更检测逻辑\n")

    test_only_documentation()
    test_only_readme()
    test_code_change()
    test_config_change()
    test_test_change()
    test_no_change()
    test_mixed_doc_only()
    test_markdown_in_docs()
    test_python_change()
    test_github_workflow()
    test_yaml_change()
    test_shell_script()

    print("\n✨ 所有测试通过！")

