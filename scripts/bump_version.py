#!/usr/bin/env python3
"""Bump the release version across every file that pins it."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (relative path, expected occurrences of the version string)
TARGETS: tuple[tuple[str, int], ...] = (
    ("pyproject.toml", 1),  # project.version
    (".claude-plugin/plugin.json", 3),  # version + 2x ENTRIX_BINARY_VERSION
    (".claude-plugin/marketplace.json", 2),  # version + asset_prefix
    ("tests/test_plugin_binary_contract.py", 1),  # hardcoded version pin
)


def _current_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if match is None:
        raise ValueError("pyproject.toml has no project version")
    return match.group(1)


def bump_version(root: Path, new_version: str) -> list[tuple[Path, int]]:
    """Replace the current version string in every pinned location atomically.

    Validates occurrence counts in all targets first; any mismatch aborts
    before a single file is written.
    """
    if re.fullmatch(r"\d+\.\d+\.\d+", new_version) is None:
        raise ValueError(f"version must be X.Y.Z, got: {new_version}")

    old_version = _current_version(root)
    if new_version == old_version:
        raise ValueError(f"version is already {old_version}")

    pending: list[tuple[Path, str, int]] = []
    for relative_path, expected_count in TARGETS:
        path = root / relative_path
        text = path.read_text(encoding="utf-8")
        count = text.count(old_version)
        if count != expected_count:
            raise ValueError(
                f"{relative_path} contains {count} occurrences of {old_version}, "
                f"expected {expected_count}"
            )
        pending.append((path, text.replace(old_version, new_version), count))

    changed: list[tuple[Path, int]] = []
    for path, new_text, count in pending:
        path.write_text(new_text, encoding="utf-8")
        changed.append((path, count))
    return changed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="new version in X.Y.Z form")
    args = parser.parse_args(argv)

    try:
        changed = bump_version(ROOT, args.version)
    except (OSError, ValueError) as error:
        print(f"版本更新失败：{error}", file=sys.stderr)
        return 1

    for path, count in changed:
        print(f"已更新 {path.relative_to(ROOT)}（{count} 处）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
