"""Detect newly added debug print calls without relying on POSIX shell tools."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DEBUG_CALL = re.compile(r"\b(?:pprint|print)\s*\(")
SOURCE_SUFFIXES = frozenset({".js", ".jsx", ".py", ".pyi", ".ts", ".tsx"})
EXPECTED_OUTPUT_MODULES = frozenset({"entrix/cli_overview.py"})


@dataclass(frozen=True)
class Finding:
    path: str
    line: str


def _normalized_path(raw_path: str) -> str:
    path = raw_path.strip()
    if path.startswith("b/"):
        path = path[2:]
    return path.replace("\\", "/")


def is_checked_source(path: str) -> bool:
    normalized_path = _normalized_path(path)
    if normalized_path in EXPECTED_OUTPUT_MODULES:
        return False
    normalized = PurePosixPath(normalized_path)
    lower_parts = tuple(part.lower() for part in normalized.parts)
    name = normalized.name.lower()
    if "docs" in lower_parts or "tests" in lower_parts or "test" in lower_parts:
        return False
    if name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts")):
        return False
    return normalized.suffix.lower() in SOURCE_SUFFIXES


def findings_from_diff(diff_text: str) -> list[Finding]:
    findings: list[Finding] = []
    current_path: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            candidate = _normalized_path(line[4:])
            current_path = None if candidate == "/dev/null" else candidate
            continue
        if (
            current_path is not None
            and line.startswith("+")
            and not line.startswith("+++")
            and is_checked_source(current_path)
            and DEBUG_CALL.search(line[1:])
        ):
            findings.append(Finding(path=current_path, line=line[1:].strip()))
    return findings


def findings_from_untracked(repo_root: Path, paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for raw_path in paths:
        path = _normalized_path(raw_path)
        if not is_checked_source(path):
            continue
        try:
            lines = (repo_root / path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        findings.extend(
            Finding(path=path, line=line.strip()) for line in lines if DEBUG_CALL.search(line)
        )
    return findings


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RuntimeError(detail)
    return result.stdout


def collect_findings(repo_root: Path, base_ref: str) -> list[Finding]:
    diff = _run_git(repo_root, "diff", "--unified=0", base_ref, "--", ".", ":(exclude)docs/**")
    untracked = _run_git(repo_root, "ls-files", "--others", "--exclude-standard").splitlines()
    return findings_from_diff(diff) + findings_from_untracked(repo_root, untracked)


def main() -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8")
        except OSError:
            pass
    repo_root = Path.cwd()
    base_ref = os.environ.get("ENTRIX_FITNESS_BASE", "HEAD")
    try:
        findings = collect_findings(repo_root, base_ref)
    except RuntimeError as error:
        sys.stderr.write(f"debug print check failed: {error}\n")
        return 2

    for finding in findings:
        sys.stdout.write(f"{finding.path}: {finding.line}\n")
    sys.stdout.write(f"new_debug_prints: {len(findings)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
