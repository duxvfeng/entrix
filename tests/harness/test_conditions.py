import pytest
import os
from pathlib import Path
from entrix.harness.conditions import evaluate_when, WhenContext


def test_files_exist_predicate():
    """测试 files_exist 谓词"""
    test_file = Path("/tmp/test_exists.txt")
    test_file.write_text("内容")

    when = {"files_exist": ["/tmp/test_exists.txt"]}
    context = WhenContext(repo_root=Path("/tmp"))

    result = evaluate_when(when, context)
    assert result is True


def test_files_exist_missing():
    """测试文件不存在时的 files_exist"""
    when = {"files_exist": ["/tmp/does_not_exist.txt"]}
    context = WhenContext(repo_root=Path("/tmp"))

    result = evaluate_when(when, context)
    assert result is False


def test_branch_predicate():
    """测试分支 include/exclude 模式"""
    when = {
        "branch": {
            "include": ["main", "feature/*"],
            "exclude": ["docs/**"]
        }
    }
    context = WhenContext(current_branch="feature/add-auth")

    result = evaluate_when(when, context)
    assert result is True


def test_branch_excluded():
    """测试分支 exclude 模式"""
    when = {
        "branch": {
            "exclude": ["docs/**"]
        }
    }
    context = WhenContext(current_branch="docs/update-readme")

    result = evaluate_when(when, context)
    assert result is False


def test_env_predicate():
    """测试环境变量谓词"""
    os.environ["TEST_VAR"] = "true"

    when = {"env": {"TEST_VAR": "true"}}
    context = WhenContext(repo_root=Path.cwd())

    result = evaluate_when(when, context)
    assert result is True


def test_env_predicate_no_match():
    """测试环境变量不匹配"""
    when = {"env": {"CI": "true"}}
    context = WhenContext(repo_root=Path.cwd())

    result = evaluate_when(when, context)
    assert result is False


def test_multiple_predicates_and_semantics():
    """测试 when 块中的多个谓词（AND 语义）"""
    os.environ["CI"] = "true"
    test_file = Path("/tmp/test_and.txt")
    test_file.write_text("内容")

    when = {
        "files_exist": ["/tmp/test_and.txt"],
        "env": {"CI": "true"}
    }
    context = WhenContext(repo_root=Path("/tmp"))

    result = evaluate_when(when, context)
    assert result is True


def test_multiple_predicates_one_false():
    """测试一个谓词为 false 时的 AND 语义"""
    when = {
        "files_exist": ["/tmp/does_not_exist.txt"],
        "env": {"CI": "true"}
    }
    context = WhenContext(repo_root=Path("/tmp"))

    result = evaluate_when(when, context)
    assert result is False


def test_empty_when():
    """测试空的 when 块始终为 true"""
    when = {}
    context = WhenContext(repo_root=Path("/tmp"))

    result = evaluate_when(when, context)
    assert result is True


def test_none_when():
    """测试 None when 始终为 true"""
    result = evaluate_when(None, WhenContext(repo_root=Path("/tmp")))
    assert result is True
