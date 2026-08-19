"""Parser for tool-produced evidence/v1 JSON documents."""
from __future__ import annotations

import json

from entrix.harness.evidence import EVIDENCE_STATUSES, Artifact
from entrix.harness.parsers.base import (
    ParserContext,
    ParserResult,
    collect_artifacts,
    resolve_workspace_file,
)


class EvidenceJsonParser:
    """Validate standard Evidence fields while leaving identity to Harness."""

    def parse(self, context: ParserContext) -> ParserResult:
        try:
            report_path = resolve_workspace_file(context.repo_root, context.config.get("path"))
            if not report_path.is_file():
                raise ValueError(f"Evidence JSON does not exist: {context.config.get('path')}")

            payload = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Evidence JSON root must be an object")
            if payload.get("schema_version") != "evidence/v1":
                raise ValueError("schema_version must be evidence/v1")

            status = payload.get("status")
            if not isinstance(status, str) or status not in EVIDENCE_STATUSES:
                raise ValueError(f"Invalid Evidence status: {status!r}")
            summary = payload.get("summary", {})
            if not isinstance(summary, dict):
                raise ValueError("Evidence summary must be an object")
            raw = payload.get("raw", {})
            if not isinstance(raw, dict):
                raise ValueError("Evidence raw must be an object")
            artifact_declarations = payload.get("artifacts", [])
            if not isinstance(artifact_declarations, list):
                raise ValueError("Evidence artifacts must be a list")

            relative_path = report_path.relative_to(context.repo_root.resolve()).as_posix()
            artifacts = [Artifact(type="evidence_json", path=relative_path)]
            artifacts.extend(collect_artifacts(context.repo_root, artifact_declarations))
            return ParserResult(
                status=status,
                summary=dict(summary),
                raw=dict(raw),
                artifacts=artifacts,
            )
        except (json.JSONDecodeError, OSError, UnicodeError, TypeError, ValueError) as error:
            return ParserResult(
                status="error", raw={"error": f"Evidence JSON parse failed: {error}"}
            )
