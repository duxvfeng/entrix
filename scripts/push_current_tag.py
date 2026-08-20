#!/usr/bin/env python3
"""Push the unique tag that already points at the current HEAD."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

SUPPORTED_REMOTES = frozenset({"github", "dxf"})


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        check=False,
        text=True,
    )


def _current_tags() -> tuple[str, ...]:
    result = _run_git(["tag", "--points-at", "HEAD"])
    if result.returncode != 0:
        detail = result.stderr.strip() or "git tag failed"
        raise RuntimeError(detail)
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def push_current_tag(remote: str) -> str:
    """Push the only local tag pointing at HEAD without creating a tag."""
    if remote not in SUPPORTED_REMOTES:
        raise ValueError(f"unsupported remote: {remote}")

    tags = _current_tags()
    if len(tags) != 1:
        found = ", ".join(tags) if tags else "none"
        raise ValueError(f"HEAD must have exactly one tag; found: {found}")

    tag = tags[0]
    result = _run_git(["push", remote, f"refs/tags/{tag}:refs/tags/{tag}"])
    if result.returncode != 0:
        detail = result.stderr.strip() or "git push failed"
        raise RuntimeError(detail)
    return tag


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", choices=sorted(SUPPORTED_REMOTES), required=True)
    args = parser.parse_args(argv)

    try:
        tag = push_current_tag(args.remote)
    except (RuntimeError, ValueError) as error:
        print(f"推送当前 tag 失败：{error}", file=sys.stderr)
        return 1

    print(f"已将当前 tag {tag} 推送到 {args.remote}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
