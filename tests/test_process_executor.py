"""Shared shell executor tests (entrix.runners.process.run_shell_command)."""

import subprocess
import sys
from pathlib import Path

import entrix.runners.process as process_module
from entrix.runners.process import run_shell_command, smart_truncate, strip_ansi


def test_run_shell_command_captures_stdout_and_stderr_separately(tmp_path: Path) -> None:
    outcome = run_shell_command(
        f'"{sys.executable}" -c "import sys; print(\'out\'); print(\'err\', file=sys.stderr)"',
        cwd=tmp_path,
    )

    assert outcome.returncode == 0
    assert outcome.timed_out is False
    assert "out" in outcome.stdout
    assert "err" in outcome.stderr
    assert outcome.duration_ms > 0


def test_run_shell_command_replaces_invalid_utf8_without_raising(tmp_path: Path) -> None:
    outcome = run_shell_command(
        f'"{sys.executable}" -c "import sys; sys.stdout.buffer.write(b\'a\\\\xffb\')"',
        cwd=tmp_path,
    )

    assert outcome.returncode == 0
    assert "a" in outcome.stdout
    assert "b" in outcome.stdout


def test_run_shell_command_reports_timeout(tmp_path: Path, monkeypatch) -> None:
    terminated = []
    monkeypatch.setattr(
        process_module,
        "terminate_process_tree",
        lambda process: terminated.append(process.pid),
    )
    process = type("Process", (), {"pid": 4321, "returncode": None})()
    process.kill = lambda: None

    def communicate(timeout=None):
        if timeout is not None:
            raise subprocess.TimeoutExpired("slow", timeout)
        return "", ""

    process.communicate = communicate
    monkeypatch.setattr(process_module.subprocess, "Popen", lambda *args, **kwargs: process)

    outcome = run_shell_command("slow-command", cwd=tmp_path, timeout_seconds=1)

    assert outcome.timed_out is True
    assert terminated == [process.pid]


def test_env_overrides_are_merged_over_process_environment(tmp_path: Path) -> None:
    outcome = run_shell_command(
        f'"{sys.executable}" -c "import os; print(os.environ.get(\'ENTRIX_TEST_VAR\', \'missing\'))"',
        cwd=tmp_path,
        env_overrides={"ENTRIX_TEST_VAR": "override"},
    )

    assert "override" in outcome.stdout


def test_smart_truncate_keeps_head_and_tail() -> None:
    text = "H" * 6000 + "MIDDLE" + "T" * 6000

    truncated = smart_truncate(text)

    assert truncated.startswith("H" * 100)
    assert truncated.endswith("T" * 100)
    assert "characters omitted" in truncated


def test_strip_ansi_removes_escape_sequences() -> None:
    assert strip_ansi("\x1b[31mred\x1b[0m plain") == "red plain"
