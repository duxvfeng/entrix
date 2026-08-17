"""Entrix subcommand hints and output-isolation tests."""
from __future__ import annotations

import pytest

from entrix.cli import build_parser, run_cli
from entrix.cli_hints import render_next_steps


@pytest.mark.parametrize(
    ("argv", "suggestion"),
    [
        (["harnes"], "entrix harness"),
        (["harness", "valdate"], "entrix harness validate"),
        (["graph", "impcat"], "entrix graph impact"),
    ],
)
def test_subcommand_typo_suggests_registered_choice(
    argv: list[str], suggestion: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(argv)

    assert error.value.code == 2
    assert f"你是否想输入：{suggestion}" in capsys.readouterr().err


def test_unrelated_subcommand_does_not_guess(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["completely-unrelated"])

    assert "你是否想输入" not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], "常用命令"),
        (["harness"], "validate"),
        (["graph"], "impact"),
        (["hook"], "file-length"),
        (["analyze"], "long-file"),
    ],
)
def test_missing_leaf_command_prints_current_group_help(
    argv: list[str], expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli(argv) == 0

    captured = capsys.readouterr()
    assert expected in captured.out
    assert captured.err == ""


def test_success_hint_uses_stderr_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("entrix.cli.cmd_harness_validate", lambda _args: 0)

    assert run_cli(["harness", "validate"]) == 0

    captured = capsys.readouterr()
    assert "下一步" not in captured.out
    assert "entrix harness run --json" in captured.err


@pytest.mark.parametrize(
    ("argv", "handler"),
    [
        (["harness", "run", "--json"], "cmd_harness_run"),
        (["run", "--output", "-"], "cmd_run"),
        (["stop-gate"], "cmd_stop_gate"),
        (["serve"], "cmd_serve"),
    ],
)
def test_machine_and_persistent_commands_do_not_emit_next_step_hints(
    argv: list[str], handler: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(f"entrix.cli.{handler}", lambda _args: 0)

    assert run_cli(argv) == 0

    captured = capsys.readouterr()
    assert "下一步" not in captured.out
    assert "下一步" not in captured.err


def test_render_next_steps_uses_declared_command_mapping() -> None:
    assert render_next_steps(("harness", "validate")) == ("entrix harness run --json",)
    assert render_next_steps(("unknown",)) == ()
