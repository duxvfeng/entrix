"""Structural queries — StructuralAnalyzer Protocol 的便捷包装。"""

from __future__ import annotations

from entrix.structure.protocol import StructuralAnalyzer


def callers_of(analyzer: StructuralAnalyzer, target: str) -> dict:
    """查找 function/method 的所有 callers。"""
    return analyzer.query("callers_of", target)


def callees_of(analyzer: StructuralAnalyzer, target: str) -> dict:
    """查找 target 调用的所有 functions/methods。"""
    return analyzer.query("callees_of", target)


def tests_for(analyzer: StructuralAnalyzer, target: str) -> dict:
    """查找覆盖 target 的 test functions。"""
    return analyzer.query("tests_for", target)


def imports_of(analyzer: StructuralAnalyzer, target: str) -> dict:
    """查找 target 所 import 的内容。"""
    return analyzer.query("imports_of", target)


def importers_of(analyzer: StructuralAnalyzer, target: str) -> dict:
    """查找哪些内容 import 了 target。"""
    return analyzer.query("importers_of", target)


def inheritors_of(analyzer: StructuralAnalyzer, target: str) -> dict:
    """查找继承自 target 的 classes。"""
    return analyzer.query("inheritors_of", target)


def file_summary(analyzer: StructuralAnalyzer, target: str) -> dict:
    """获取文件的 structural summary。"""
    return analyzer.query("file_summary", target)
