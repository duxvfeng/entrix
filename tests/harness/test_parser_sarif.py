"""SARIF evidence parser tests."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from entrix.harness.parsers import get_parser
from entrix.harness.parsers.base import ParserContext


def parse_sarif(repo_root: Path, config: dict[str, object] | None = None):
    process = subprocess.CompletedProcess("test-command", 0, "", "")
    parser_config = {"path": "scan.sarif", **(config or {})}
    return get_parser("sarif").parse(ParserContext(repo_root, parser_config, process))


def write_sarif(path: Path, runs: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"version": "2.1.0", "runs": runs}),
        encoding="utf-8",
    )


def test_sarif_fails_when_blocking_level_is_present(tmp_path: Path) -> None:
    write_sarif(
        tmp_path / "scan.sarif",
        [
            {
                "results": [
                    {"ruleId": "rule-a", "level": "warning"},
                    {"ruleId": "rule-b", "level": "error"},
                    {"ruleId": "rule-a", "level": "note"},
                ]
            }
        ],
    )

    result = parse_sarif(tmp_path)

    assert result.status == "fail"
    assert result.summary == {
        "runs": 1,
        "results": 3,
        "errors": 1,
        "warnings": 1,
        "notes": 1,
        "none": 0,
        "rules": 2,
    }
    assert [(artifact.type, artifact.path) for artifact in result.artifacts] == [
        ("sarif", "scan.sarif")
    ]


def test_sarif_aggregates_runs_and_uses_warning_for_missing_level(
    tmp_path: Path,
) -> None:
    write_sarif(
        tmp_path / "scan.sarif",
        [
            {"results": [{"ruleId": "rule-a"}]},
            {"results": [{"ruleId": "rule-b", "level": "note"}]},
        ],
    )

    result = parse_sarif(tmp_path, {"blocking_levels": ["warning"]})

    assert result.status == "fail"
    assert result.summary["runs"] == 2
    assert result.summary["warnings"] == 1
    assert result.summary["notes"] == 1


def test_sarif_passes_with_no_results(tmp_path: Path) -> None:
    write_sarif(tmp_path / "scan.sarif", [])

    result = parse_sarif(tmp_path)

    assert result.status == "pass"
    assert result.summary["runs"] == 0
    assert result.summary["results"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"version": "2.1.0", "runs": {}},
        {"version": "2.1.0", "runs": [None]},
        {"version": "2.1.0", "runs": [{"results": {}}]},
        {"version": "2.1.0", "runs": [{"results": [None]}]},
        {"version": "2.1.0", "runs": [{"results": [{"level": "fatal"}]}]},
    ],
)
def test_sarif_rejects_malformed_structure(
    tmp_path: Path, payload: object
) -> None:
    (tmp_path / "scan.sarif").write_text(json.dumps(payload), encoding="utf-8")

    result = parse_sarif(tmp_path)

    assert result.status == "error"


@pytest.mark.parametrize("path", ["missing.sarif", "../scan.sarif"])
def test_sarif_rejects_missing_or_escaped_report(tmp_path: Path, path: str) -> None:
    result = parse_sarif(tmp_path, {"path": path})

    assert result.status == "error"
