"""Tests for pushing the latest existing tag reachable from HEAD."""

from __future__ import annotations

from subprocess import CompletedProcess

import pytest

import scripts.push_current_tag as push_current_tag


def test_push_current_tag_uses_latest_reachable_existing_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_git(args: list[str]) -> CompletedProcess[str]:
        commands.append(args)
        if args == ["describe", "--tags", "--abbrev=0", "HEAD"]:
            return CompletedProcess(args, 0, stdout="v0.1.21\n", stderr="")
        return CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(push_current_tag, "_run_git", fake_git)

    assert push_current_tag.push_current_tag("github") == "v0.1.21"
    assert commands == [
        ["describe", "--tags", "--abbrev=0", "HEAD"],
        ["push", "github", "refs/tags/v0.1.21:refs/tags/v0.1.21"],
    ]


def test_push_current_tag_rejects_missing_reachable_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        push_current_tag,
        "_run_git",
        lambda args: CompletedProcess(
            args,
            128,
            stdout="",
            stderr="fatal: No names found, cannot describe anything.\n",
        ),
    )

    with pytest.raises(ValueError, match="no existing tag"):
        push_current_tag.push_current_tag("dxf")


def test_push_current_tag_rejects_unknown_remote() -> None:
    with pytest.raises(ValueError, match="unsupported remote"):
        push_current_tag.push_current_tag("origin")
