"""用于风险变更人工升级的 review-trigger 规则。"""

from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DiffStats:
    """review-trigger 评估的聚合 diff 统计。"""

    file_count: int = 0
    added_lines: int = 0
    deleted_lines: int = 0


@dataclass(frozen=True)
class ReviewTriggerRule:
    """一条 review-trigger 规则。"""

    name: str
    type: str
    severity: str = "medium"
    action: str = "require_human_review"
    paths: tuple[str, ...] = ()
    directories: tuple[str, ...] = ()
    max_files: int | None = None
    max_added_lines: int | None = None
    max_deleted_lines: int | None = None
    evidence_paths: tuple[str, ...] = ()
    boundaries: tuple[tuple[str, tuple[str, ...]], ...] = ()
    min_boundaries: int = 2


@dataclass(frozen=True)
class TriggerMatch:
    """一条被触发的规则，附带人类可读的原因。"""

    name: str
    severity: str
    action: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewTriggerReport:
    """review-trigger 评估的结构化结果。"""

    human_review_required: bool
    base: str
    changed_files: tuple[str, ...] = ()
    diff_stats: DiffStats = field(default_factory=DiffStats)
    triggers: tuple[TriggerMatch, ...] = ()

    def to_dict(self) -> dict:
        """将报告序列化为 JSON 友好字典。"""
        data = asdict(self)
        data["changed_files"] = list(self.changed_files)
        data["triggers"] = [
            {
                "name": trigger.name,
                "severity": trigger.severity,
                "action": trigger.action,
                "reasons": list(trigger.reasons),
            }
            for trigger in self.triggers
        ]
        return data


def parse_review_trigger_rules(raw_rules: object) -> list[ReviewTriggerRule]:
    """Parse inline review-trigger mappings into domain rules."""
    if not isinstance(raw_rules, list):
        raise ValueError("review_triggers.rules 必须是列表")
    rules: list[ReviewTriggerRule] = []
    names: set[str] = set()
    for index, entry in enumerate(raw_rules):
        if not isinstance(entry, dict):
            raise ValueError(f"review_triggers.rules[{index}] 必须是对象")
        name = entry.get("name")
        rule_type = entry.get("type")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"review_triggers.rules[{index}].name 必须是非空字符串")
        if not isinstance(rule_type, str) or not rule_type.strip():
            raise ValueError(f"review_triggers.rules[{index}].type 必须是非空字符串")
        if name in names:
            raise ValueError(f"review_triggers.rules 存在重复 name：{name}")
        names.add(name)
        raw_boundaries = entry.get("boundaries", {}) or {}
        if not isinstance(raw_boundaries, dict):
            raise ValueError(f"review_triggers.rules[{index}].boundaries 必须是对象")
        boundaries: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
            (name, tuple(patterns or ()))
            for name, patterns in raw_boundaries.items()
            if isinstance(name, str)
        )
        rules.append(
            ReviewTriggerRule(
                name=name,
                type=rule_type,
                severity=entry.get("severity", "medium"),
                action=entry.get("action", "require_human_review"),
                paths=tuple(entry.get("paths", [])),
                directories=tuple(entry.get("directories", [])),
                max_files=entry.get("max_files"),
                max_added_lines=entry.get("max_added_lines"),
                max_deleted_lines=entry.get("max_deleted_lines"),
                evidence_paths=tuple(entry.get("evidence_paths", [])),
                boundaries=boundaries,
                min_boundaries=int(entry.get("min_boundaries", 2)),
            )
        )
    return rules


def collect_changed_files(repo_root: Path, base: str) -> list[str]:
    """收集相对于 git base 的变更和未跟踪文件。"""
    files: list[str] = []
    commands = [
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base],
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        files.extend(line.strip() for line in result.stdout.splitlines() if line.strip())

    seen: set[str] = set()
    deduped: list[str] = []
    for file_path in files:
        if file_path not in seen:
            seen.add(file_path)
            deduped.append(file_path)
    return deduped


def collect_diff_stats(repo_root: Path, base: str) -> DiffStats:
    """收集相对于 git base 的聚合 diff 统计。"""
    result = subprocess.run(
        ["git", "diff", "--numstat", "--diff-filter=ACMR", base],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    added_lines = 0
    deleted_lines = 0
    file_count = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, _path = parts
        if added == "-" or deleted == "-":
            continue
        file_count += 1
        added_lines += int(added)
        deleted_lines += int(deleted)
    return DiffStats(file_count=file_count, added_lines=added_lines, deleted_lines=deleted_lines)


def _changed_files_in_directory(changed_files: list[str], directory: str) -> list[str]:
    normalized = directory.strip().strip("/")
    if not normalized:
        return []
    prefix = f"{normalized}/"
    return [
        file_path for file_path in changed_files if file_path == normalized or file_path.startswith(prefix)
    ]


def _count_direct_files(repo_root: Path, directory: str) -> int:
    target = (repo_root / directory).resolve()
    if not target.exists() or not target.is_dir():
        return 0
    return sum(1 for child in target.iterdir() if child.is_file())


def evaluate_review_triggers(
    rules: list[ReviewTriggerRule],
    changed_files: list[str],
    diff_stats: DiffStats,
    *,
    base: str,
    repo_root: Path | None = None,
) -> ReviewTriggerReport:
    """针对一次 diff 评估 review-trigger 规则。"""
    triggers: list[TriggerMatch] = []
    for rule in rules:
        if rule.type == "changed_paths":
            reasons = tuple(
                f"changed path: {file_path}"
                for file_path in changed_files
                if any(fnmatch.fnmatch(file_path, pattern) for pattern in rule.paths)
            )
            if reasons:
                triggers.append(
                    TriggerMatch(
                        name=rule.name,
                        severity=rule.severity,
                        action=rule.action,
                        reasons=reasons,
                    )
                )
        elif rule.type == "sensitive_file_change":
            reasons = tuple(
                f"sensitive file changed: {file_path}"
                for file_path in changed_files
                if any(fnmatch.fnmatch(file_path, pattern) for pattern in rule.paths)
            )
            if reasons:
                triggers.append(
                    TriggerMatch(
                        name=rule.name,
                        severity=rule.severity,
                        action=rule.action,
                        reasons=reasons,
                    )
                )
        elif rule.type == "diff_size":
            reasons: list[str] = []
            if rule.max_files is not None and diff_stats.file_count > rule.max_files:
                reasons.append(
                    f"diff touched {diff_stats.file_count} files (threshold: {rule.max_files})"
                )
            if (
                rule.max_added_lines is not None
                and diff_stats.added_lines > rule.max_added_lines
            ):
                reasons.append(
                    f"diff added {diff_stats.added_lines} lines (threshold: {rule.max_added_lines})"
                )
            if (
                rule.max_deleted_lines is not None
                and diff_stats.deleted_lines > rule.max_deleted_lines
            ):
                reasons.append(
                    "diff deleted "
                    f"{diff_stats.deleted_lines} lines (threshold: {rule.max_deleted_lines})"
                )
            if reasons:
                triggers.append(
                    TriggerMatch(
                        name=rule.name,
                        severity=rule.severity,
                        action=rule.action,
                        reasons=tuple(reasons),
                    )
                )
        elif rule.type == "directory_file_count":
            if repo_root is None or rule.max_files is None:
                continue
            reasons: list[str] = []
            for directory in rule.directories:
                touched_files = _changed_files_in_directory(changed_files, directory)
                if not touched_files:
                    continue
                file_count = _count_direct_files(repo_root, directory)
                if file_count > rule.max_files:
                    changed_sample = ", ".join(touched_files[:3])
                    if len(touched_files) > 3:
                        changed_sample += ", ..."
                    reasons.append(
                        f"directory '{directory}' has {file_count} direct files "
                        f"(threshold: {rule.max_files}); changed files: {changed_sample}"
                    )
            if reasons:
                triggers.append(
                    TriggerMatch(
                        name=rule.name,
                        severity=rule.severity,
                        action=rule.action,
                        reasons=tuple(reasons),
                    )
                )
        elif rule.type == "evidence_gap":
            monitored_changes = [
                file_path
                for file_path in changed_files
                if any(fnmatch.fnmatch(file_path, pattern) for pattern in rule.paths)
            ]
            if not monitored_changes:
                continue
            evidence_touched = any(
                fnmatch.fnmatch(file_path, pattern)
                for file_path in changed_files
                for pattern in rule.evidence_paths
            )
            if not evidence_touched:
                reasons = tuple(
                    [f"changed code path without evidence update: {path}" for path in monitored_changes]
                    + [f"expected evidence path patterns: {', '.join(rule.evidence_paths)}"]
                )
                triggers.append(
                    TriggerMatch(
                        name=rule.name,
                        severity=rule.severity,
                        action=rule.action,
                        reasons=reasons,
                    )
                )
        elif rule.type == "cross_boundary_change":
            boundary_hits: dict[str, list[str]] = {}
            for boundary_name, patterns in rule.boundaries:
                matches = [
                    file_path
                    for file_path in changed_files
                    if any(fnmatch.fnmatch(file_path, pattern) for pattern in patterns)
                ]
                if matches:
                    boundary_hits[boundary_name] = matches
            if len(boundary_hits) >= rule.min_boundaries:
                reasons = tuple(
                    f"changed boundary '{boundary_name}': {', '.join(paths)}"
                    for boundary_name, paths in boundary_hits.items()
                )
                triggers.append(
                    TriggerMatch(
                        name=rule.name,
                        severity=rule.severity,
                        action=rule.action,
                        reasons=reasons,
                    )
                )

    return ReviewTriggerReport(
        human_review_required=bool(triggers),
        base=base,
        changed_files=tuple(changed_files),
        diff_stats=diff_stats,
        triggers=tuple(triggers),
    )
