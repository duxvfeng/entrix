"""SARIF 2.x report parser."""
from __future__ import annotations

import json

from entrix.errors import ConfigError
from entrix.harness.evidence import Artifact
from entrix.harness.parsers.base import ParserContext, ParserResult, resolve_workspace_file

SARIF_LEVELS = frozenset({"error", "warning", "note", "none"})


class SarifParser:
    """Aggregate SARIF runs into normalized static-analysis evidence."""

    def parse(self, context: ParserContext) -> ParserResult:
        try:
            report_path = resolve_workspace_file(context.repo_root, context.config.get("path"))
            if not report_path.is_file():
                raise ConfigError(f"SARIF report does not exist: {context.config.get('path')}")

            payload = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ConfigError("SARIF root must be an object")
            runs = payload.get("runs")
            if not isinstance(runs, list):
                raise ConfigError("SARIF runs must be a list")

            blocking_levels = _blocking_levels(context.config.get("blocking_levels", ["error"]))
            counts = {level: 0 for level in SARIF_LEVELS}
            rule_ids: set[str] = set()
            result_count = 0
            for run_index, run in enumerate(runs):
                if not isinstance(run, dict):
                    raise ConfigError(f"SARIF runs[{run_index}] must be an object")
                results = run.get("results", [])
                if not isinstance(results, list):
                    raise ConfigError(f"SARIF runs[{run_index}].results must be a list")
                for result_index, result in enumerate(results):
                    if not isinstance(result, dict):
                        raise ConfigError(
                            f"SARIF runs[{run_index}].results[{result_index}] must be an object"
                        )
                    level = result["level"] if "level" in result else "warning"
                    if level not in SARIF_LEVELS:
                        raise ConfigError(f"Invalid SARIF level: {level!r}")
                    counts[level] += 1
                    result_count += 1
                    rule_id = result.get("ruleId")
                    if rule_id is not None:
                        if not isinstance(rule_id, str) or not rule_id:
                            raise ConfigError("SARIF ruleId must be a non-empty string")
                        rule_ids.add(rule_id)

            relative_path = report_path.relative_to(context.repo_root.resolve()).as_posix()
            blocked = any(counts[level] > 0 for level in blocking_levels)
            return ParserResult(
                status="fail" if blocked else "pass",
                summary={
                    "runs": len(runs),
                    "results": result_count,
                    "errors": counts["error"],
                    "warnings": counts["warning"],
                    "notes": counts["note"],
                    "none": counts["none"],
                    "rules": len(rule_ids),
                },
                raw={"path": relative_path, "blocking_levels": sorted(blocking_levels)},
                artifacts=[Artifact(type="sarif", path=relative_path)],
            )
        except (json.JSONDecodeError, OSError, UnicodeError, TypeError, ValueError) as error:
            return ParserResult(status="error", raw={"error": f"SARIF parse failed: {error}"})


def _blocking_levels(value: object) -> set[str]:
    if not isinstance(value, list):
        raise ConfigError("SARIF blocking_levels must be a list")
    levels: set[str] = set()
    for level in value:
        if level not in SARIF_LEVELS:
            raise ConfigError(f"Invalid SARIF blocking level: {level!r}")
        levels.add(level)
    return levels
