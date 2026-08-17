from pathlib import Path
from entrix.harness.conditions import evaluate_when, WhenContext, _changed_any


def test_files_exist_predicate(tmp_path):
    """测试 files_exist 谓词"""
    test_file = tmp_path / "test_exists.txt"
    test_file.write_text("内容")

    when = {"files_exist": ["test_exists.txt"]}
    context = WhenContext(repo_root=tmp_path)

    result = evaluate_when(when, context)
    assert result is True


def test_files_exist_missing(tmp_path):
    """测试文件不存在时的 files_exist"""
    when = {"files_exist": ["does_not_exist.txt"]}
    context = WhenContext(repo_root=tmp_path)

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


def test_env_predicate(monkeypatch):
    """测试环境变量谓词"""
    monkeypatch.setenv("TEST_VAR", "true")

    when = {"env": {"TEST_VAR": "true"}}
    context = WhenContext(repo_root=Path.cwd())

    result = evaluate_when(when, context)
    assert result is True


def test_env_predicate_no_match(monkeypatch):
    """测试环境变量不匹配"""
    monkeypatch.delenv("CI", raising=False)

    when = {"env": {"CI": "true"}}
    context = WhenContext(repo_root=Path.cwd())

    result = evaluate_when(when, context)
    assert result is False


def test_multiple_predicates_and_semantics(tmp_path, monkeypatch):
    """测试 when 块中的多个谓词（AND 语义）"""
    monkeypatch.setenv("CI", "true")
    test_file = tmp_path / "test_and.txt"
    test_file.write_text("内容")

    when = {
        "files_exist": ["test_and.txt"],
        "env": {"CI": "true"}
    }
    context = WhenContext(repo_root=tmp_path)

    result = evaluate_when(when, context)
    assert result is True


def test_multiple_predicates_one_false(tmp_path, monkeypatch):
    """测试一个谓词为 false 时的 AND 语义"""
    monkeypatch.setenv("CI", "true")
    when = {
        "files_exist": ["does_not_exist.txt"],
        "env": {"CI": "true"}
    }
    context = WhenContext(repo_root=tmp_path)

    result = evaluate_when(when, context)
    assert result is False


def test_empty_when(tmp_path):
    """测试空的 when 块始终为 true"""
    when = {}
    context = WhenContext(repo_root=tmp_path)

    result = evaluate_when(when, context)
    assert result is True


def test_none_when(tmp_path):
    """测试 None when 始终为 true"""
    result = evaluate_when(None, WhenContext(repo_root=tmp_path))
    assert result is True


def test_changed_any_matching_pattern():
    """测试 _changed_any 匹配变更文件"""
    context = WhenContext(changed_files=["src/main.py", "tests/test.py"])
    assert _changed_any(["src/*.py"], context) is True


def test_changed_any_non_matching_pattern():
    """测试 _changed_any 不匹配的模式"""
    context = WhenContext(changed_files=["docs/readme.md"])
    assert _changed_any(["src/*.py"], context) is False


def test_changed_any_empty_changed_files():
    """测试 _changed_any 空 changed_files 列表"""
    context = WhenContext(changed_files=[])
    assert _changed_any(["src/*.py"], context) is False
