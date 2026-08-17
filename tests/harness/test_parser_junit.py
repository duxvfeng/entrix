"""JUnit XML evidence parser tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

from entrix.harness.parsers import get_parser
from entrix.harness.parsers.base import ParserContext


def parse_junit(repo_root: Path, path: str = "junit.xml"):
    process = subprocess.CompletedProcess("test-command", 0, "", "")
    context = ParserContext(repo_root, {"type": "junit", "path": path}, process)
    return get_parser("junit").parse(context)


def test_junit_aggregates_multiple_suites(tmp_path: Path) -> None:
    (tmp_path / "junit.xml").write_text(
        '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="1" time="1.5" />'
        '<testsuite tests="2" failures="0" errors="0" skipped="0" time="0.5" /></testsuites>',
        encoding="utf-8",
    )

    result = parse_junit(tmp_path)

    assert result.status == "fail"
    assert result.summary == {
        "total": 5,
        "passed": 3,
        "failed": 1,
        "errors": 0,
        "skipped": 1,
        "duration_seconds": 2.0,
    }
    assert [(artifact.type, artifact.path) for artifact in result.artifacts] == [
        ("junit", "junit.xml")
    ]


def test_junit_passes_without_failures_or_errors(tmp_path: Path) -> None:
    (tmp_path / "junit.xml").write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0" time="0.25" />',
        encoding="utf-8",
    )

    result = parse_junit(tmp_path)

    assert result.status == "pass"
    assert result.summary["passed"] == 2


def test_junit_missing_report_returns_error(tmp_path: Path) -> None:
    result = parse_junit(tmp_path)

    assert result.status == "error"
    assert "不存在" in str(result.raw["error"])


def test_junit_malformed_xml_returns_error(tmp_path: Path) -> None:
    (tmp_path / "junit.xml").write_text("<testsuite>", encoding="utf-8")

    result = parse_junit(tmp_path)

    assert result.status == "error"
    assert "JUnit" in str(result.raw["error"])


def test_junit_rejects_workspace_escape(tmp_path: Path) -> None:
    result = parse_junit(tmp_path, "../junit.xml")

    assert result.status == "error"
    assert "工作区" in str(result.raw["error"])
