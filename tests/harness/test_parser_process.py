"""Process parser registry tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from entrix.harness.parsers import get_parser
from entrix.harness.parsers.base import ParserContext, resolve_workspace_file


def parse_with(
    parser_type: str,
    repo_root: Path,
    config: dict[str, object],
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
):
    process = subprocess.CompletedProcess(
        args="test-command",
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
    context = ParserContext(
        repo_root=repo_root,
        config=config,
        completed_process=process,
    )
    return get_parser(parser_type).parse(context)


def test_registry_rejects_unknown_parser() -> None:
    with pytest.raises(ValueError, match="parser"):
        get_parser("python_eval")


def test_resolve_workspace_file_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="工作区"):
        resolve_workspace_file(tmp_path, "../report.xml")


def test_exit_code_parser_preserves_process_output(tmp_path: Path) -> None:
    result = parse_with(
        "exit_code",
        tmp_path,
        {"type": "exit_code"},
        stdout="passed",
        stderr="warning",
    )

    assert result.status == "pass"
    assert result.raw == {"exit_code": 0, "stdout": "passed", "stderr": "warning"}


def test_exit_code_parser_maps_nonzero_to_fail(tmp_path: Path) -> None:
    result = parse_with("exit_code", tmp_path, {"type": "exit_code"}, returncode=3)

    assert result.status == "fail"


def test_regex_parser_coerces_named_numeric_captures(tmp_path: Path) -> None:
    result = parse_with(
        "regex",
        tmp_path,
        {"type": "regex", "pattern": r"passed=(?P<passed>\d+), ratio=(?P<ratio>\d+\.\d+)"},
        stdout="passed=12, ratio=0.75",
    )

    assert result.status == "pass"
    assert result.summary == {"passed": 12, "ratio": 0.75}
