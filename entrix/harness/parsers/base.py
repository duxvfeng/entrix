"""Shared parser contracts and workspace path safety."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from entrix.harness.evidence import Artifact


@dataclass(frozen=True)
class ParserContext:
    """Inputs available to one evidence parser."""

    repo_root: Path
    config: dict[str, Any]
    completed_process: subprocess.CompletedProcess[str]


@dataclass
class ParserResult:
    """Normalized facts returned by an evidence parser."""

    status: str
    summary: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)


class EvidenceParser(Protocol):
    """Protocol implemented by all registered evidence parsers."""

    def parse(self, context: ParserContext) -> ParserResult:
        """Convert raw producer output into normalized evidence fields."""


def resolve_workspace_file(repo_root: Path, raw_path: object) -> Path:
    """Resolve a relative path and reject workspace escapes."""
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("artifact 路径必须是非空字符串")
    relative_path = Path(raw_path)
    root = repo_root.resolve()
    if relative_path.is_absolute():
        raise ValueError(f"artifact 路径必须位于工作区内：{raw_path}")
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"artifact 路径必须位于工作区内：{raw_path}")
    return resolved


def collect_artifacts(repo_root: Path, declarations: object) -> list[Artifact]:
    """Validate configured artifact declarations and normalize their paths."""
    if declarations is None:
        return []
    if not isinstance(declarations, list):
        raise ValueError("artifacts 必须是列表")

    root = repo_root.resolve()
    artifacts: list[Artifact] = []
    for index, declaration in enumerate(declarations):
        if not isinstance(declaration, dict):
            raise ValueError(f"artifacts[{index}] 必须是对象")
        artifact_type = declaration.get("type")
        if not isinstance(artifact_type, str) or not artifact_type:
            raise ValueError(f"artifacts[{index}].type 必须是非空字符串")
        artifact_path = resolve_workspace_file(root, declaration.get("path"))
        if not artifact_path.is_file():
            raise ValueError(f"artifact 文件不存在：{declaration.get('path')}")
        metadata = declaration.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"artifacts[{index}].metadata 必须是对象")
        artifacts.append(
            Artifact(
                type=artifact_type,
                path=artifact_path.relative_to(root).as_posix(),
                metadata=dict(metadata),
            )
        )
    return artifacts
