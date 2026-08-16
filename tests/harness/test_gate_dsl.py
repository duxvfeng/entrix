"""Gate DSL expression evaluator tests."""
import pytest
from entrix.harness.gate.dsl import evaluate_condition
from entrix.harness.evidence import Evidence


def test_simple_equality():
    """测试简单相等条件"""
    evidence = Evidence(id="test-1", status="pass")
    result = evaluate_condition('status == "pass"', evidence)
    assert result is True


def test_string_equality_false():
    """测试失败的字符串相等"""
    evidence = Evidence(id="test-1", status="fail")
    result = evaluate_condition('status == "pass"', evidence)
    assert result is False


def test_comparison_operators():
    """测试比较运算符"""
    evidence = Evidence(id="test-1", summary={"score": 85})

    assert evaluate_condition("summary.score > 80", evidence) is True
    assert evaluate_condition("summary.score >= 85", evidence) is True
    assert evaluate_condition("summary.score < 90", evidence) is True
    assert evaluate_condition("summary.score <= 85", evidence) is True


def test_arithmetic_operations():
    """测试算术运算"""
    evidence = Evidence(id="test-1", summary={"a": 10, "b": 5})

    assert evaluate_condition("summary.a + summary.b > 10", evidence) is True
    assert evaluate_condition("summary.a - summary.b == 5", evidence) is True
    assert evaluate_condition("summary.a * summary.b == 50", evidence) is True
    assert evaluate_condition("summary.a / summary.b == 2", evidence) is True


def test_logical_operators():
    """测试逻辑运算符"""
    evidence = Evidence(id="test-1", status="pass", summary={"score": 85})

    assert evaluate_condition('status == "pass" and summary.score > 80', evidence) is True
    assert evaluate_condition('status == "pass" or summary.score > 90', evidence) is True
    assert evaluate_condition('not (status == "fail")', evidence) is True


def test_in_operator():
    """测试 'in' 运算符"""
    evidence = Evidence(id="test-1", summary={"categories": ["security", "performance"]})

    assert evaluate_condition('"security" in summary.categories', evidence) is True
    assert evaluate_condition('"documentation" in summary.categories', evidence) is False


def test_parentheses():
    """测试括号分组"""
    evidence = Evidence(id="test-1", status="pass", summary={"score": 85})

    result = evaluate_condition('(status == "pass" or status == "skipped") and summary.score > 80', evidence)
    assert result is True


def test_nested_field_access():
    """测试嵌套字段访问"""
    evidence = Evidence(id="test-1", summary={"nested": {"deep": {"value": 42}}})

    result = evaluate_condition("summary.nested.deep.value == 42", evidence)
    assert result is True