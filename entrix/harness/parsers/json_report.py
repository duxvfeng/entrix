"""Declarative JSON report parser."""
from __future__ import annotations

import json

from entrix.harness.evidence import EVIDENCE_STATUSES, Artifact
from entrix.harness.parsers.base import ParserContext, ParserResult, resolve_workspace_file


class JsonReportParser:
    """Map JSON report paths to normalized status and summary fields."""

    def parse(self, context: ParserContext) -> ParserResult:
        try:
            report_path = resolve_workspace_file(context.repo_root, context.config.get("path"))
            if not report_path.is_file():
                raise ValueError(f"JSON report does not exist: {context.config.get('path')}")

            payload = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON report root must be an object")

            status_path = _non_empty_text(context.config.get("status_path"), "status_path")
            status_map = context.config.get("status_map")
            if not isinstance(status_map, dict):
                raise ValueError("status_map must be an object")
            source_status = read_path(payload, status_path)
            if not isinstance(source_status, str) or source_status not in status_map:
                raise ValueError(f"Unmapped JSON status: {source_status!r}")
            status = status_map[source_status]
            if status not in EVIDENCE_STATUSES:
                raise ValueError(f"Invalid mapped Evidence status: {status!r}")

            summary_config = context.config.get("summary", {})
            if not isinstance(summary_config, dict):
                raise ValueError("summary must be an object")
            summary: dict[str, object] = {}
            for field, source_path in summary_config.items():
                field_name = _non_empty_text(field, "summary field")
                path = _non_empty_text(source_path, f"summary.{field_name}")
                summary[field_name] = read_path(payload, path)

            relative_path = report_path.relative_to(context.repo_root.resolve()).as_posix()
            return ParserResult(
                status=status,
                summary=summary,
                raw={"path": relative_path, "source_status": source_status},
                artifacts=[Artifact(type="json", path=relative_path)],
            )
        except (json.JSONDecodeError, OSError, UnicodeError, TypeError, ValueError) as error:
            return ParserResult(status="error", raw={"error": f"JSON parse failed: {error}"})


def read_path(data: object, path: str) -> object:
    """Read a dotted dict/list path without evaluating expressions."""
    if not path or any(not segment for segment in path.split(".")):
        raise ValueError(f"Invalid JSON path: {path!r}")

    current = data
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                raise ValueError(f"JSON path does not exist: {path}")
            current = current[segment]
            continue
        if isinstance(current, list):
            if not segment.isdigit():
                raise ValueError(f"JSON list path requires an index: {path}")
            index = int(segment)
            if index >= len(current):
                raise ValueError(f"JSON path does not exist: {path}")
            current = current[index]
            continue
        raise ValueError(f"JSON path does not exist: {path}")
    return current


def _non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
