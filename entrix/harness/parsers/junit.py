"""JUnit XML report parser."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from entrix.harness.evidence import Artifact
from entrix.harness.parsers.base import ParserContext, ParserResult, resolve_workspace_file


class JUnitParser:
    """Aggregate JUnit test suites into stable test evidence."""

    def parse(self, context: ParserContext) -> ParserResult:
        try:
            report_path = resolve_workspace_file(context.repo_root, context.config.get("path"))
            if not report_path.is_file():
                raise ValueError(f"JUnit 报告不存在：{context.config.get('path')}")
            root = ET.parse(report_path).getroot()
            suites = _leaf_suites(root)
            if not suites:
                raise ValueError("JUnit 报告不包含 testsuite")
            total = sum(_integer(suite, "tests") for suite in suites)
            failed = sum(_integer(suite, "failures") for suite in suites)
            errors = sum(_integer(suite, "errors") for suite in suites)
            skipped = sum(_integer(suite, "skipped") for suite in suites)
            duration = sum(_decimal(suite, "time") for suite in suites)
            passed = max(total - failed - errors - skipped, 0)
            relative_path = report_path.relative_to(context.repo_root.resolve()).as_posix()
            return ParserResult(
                status="fail" if failed + errors else "pass",
                summary={
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "skipped": skipped,
                    "duration_seconds": duration,
                },
                raw={"path": relative_path},
                artifacts=[Artifact(type="junit", path=relative_path)],
            )
        except (ET.ParseError, OSError, TypeError, ValueError) as error:
            return ParserResult(status="error", raw={"error": f"JUnit 解析失败：{error}"})


def _leaf_suites(root: ET.Element) -> list[ET.Element]:
    suites = [element for element in root.iter() if _tag(element) == "testsuite"]
    return [
        suite
        for suite in suites
        if not any(_tag(descendant) == "testsuite" for descendant in list(suite))
    ]


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _integer(element: ET.Element, attribute: str) -> int:
    value = int(element.attrib.get(attribute, "0"))
    if value < 0:
        raise ValueError(f"JUnit {attribute} 不能为负数")
    return value


def _decimal(element: ET.Element, attribute: str) -> float:
    value = float(element.attrib.get(attribute, "0"))
    if value < 0:
        raise ValueError(f"JUnit {attribute} 不能为负数")
    return value
