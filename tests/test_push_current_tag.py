"""Tests for pushing the tag that already points at HEAD."""

from __future__ import annotations

from subprocess import CompletedProcess

import pytest

import scripts.push_current_tag as push_current_tag


def test_push_current_tag_uses_only_the_unique_tag_on_head(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake_git(args: list[str]) -> CompletedProcess[str]:
        commands.append(args)
        if args == ["tag", "--points-at", "HEAD"]:
            return CompletedProcess(args, 0, stdout="v0.1.21\n", stderr="")
        return CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(push_current_tag, "_run_git", fake_git)

    assert push_current_tag.push_current_tag("github") == "v0.1.21"
    assert commands == [
        ["tag", "--points-at", "HEAD"],
        ["push", "github", "refs/tags/v0.1.21:refs/tags/v0.1.21"],
    ]


@pytest.mark.parametrize("tag_output", ["", "v0.1.20\nv0.1.21\n"])
def test_push_current_tag_rejects_missing_or_ambiguous_tag(
    monkeypatch: pytest.MonkeyPatch, tag_output: str
) -> None:
    monkeypatch.setattr(
        push_current_tag,
        "_run_git",
        lambda args: CompletedProcess(args, 0, stdout=tag_output, stderr=""),
    )

    with pytest.raises(ValueError, match="exactly one tag"):
        push_current_tag.push_current_tag("dxf")


def test_push_current_tag_rejects_unknown_remote() -> None:
    with pytest.raises(ValueError, match="unsupported remote"):
        push_current_tag.push_current_tag("origin")
