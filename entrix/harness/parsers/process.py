"""Parsers for command exit codes and stdout regex captures."""
from __future__ import annotations

import re

from entrix.harness.parsers.base import ParserContext, ParserResult


class ExitCodeParser:
    """Map a process return code to pass or fail evidence."""

    def parse(self, context: ParserContext) -> ParserResult:
        process = context.completed_process
        return ParserResult(
            status="pass" if process.returncode == 0 else "fail",
            raw={
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            },
        )


class RegexParser:
    """Extract normalized summary fields from named regex captures."""

    def parse(self, context: ParserContext) -> ParserResult:
        process = context.completed_process
        raw = {
            "exit_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        pattern = context.config.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return ParserResult(status="error", raw={"error": "Regex parser requires pattern"})
        try:
            match = re.search(pattern, process.stdout)
        except re.error as error:
            return ParserResult(status="error", raw={"error": f"Regex error: {error}"})
        if match is None:
            return ParserResult(status="error", raw={"error": "Regex pattern did not match output"})
        return ParserResult(
            status="pass",
            summary={key: _coerce_capture(value) for key, value in match.groupdict().items()},
            raw=raw,
        )


def _coerce_capture(value: str | None) -> object:
    if value is None:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value
