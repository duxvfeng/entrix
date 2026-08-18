"""Tests for entrix.runners.shell."""

from datetime import date, timedelta
from concurrent.futures import Future
from pathlib import Path
import subprocess
import sys

from entrix.model import Metric, ResultState, Waiver
import entrix.runners.shell as shell_module
import entrix.runners.process as process_module
from entrix.runners.shell import ShellRunner


def test_run_uses_current_platform_shell(tmp_path):
    runner = ShellRunner(tmp_path)
    metric = Metric(
        name="portable",
        command=f'"{sys.executable}" -c "import sys; sys.exit(1)"',
        hard_gate=True,
    )

    result = runner.run(metric)

    assert result.returncode == 1
    assert result.state == ResultState.FAIL


def test_dry_run():
    runner = ShellRunner(Path("/tmp"))
    m = Metric(name="test", command="echo hello")
    result = runner.run(m, dry_run=True)
    assert result.passed is True
    assert "[DRY-RUN]" in result.output
    assert result.metric_name == "test"


def test_run_success_exit_code():
    runner = ShellRunner(Path("/tmp"))
    m = Metric(name="echo_test", command="echo ok")
    result = runner.run(m)
    assert result.passed is True
    assert "ok" in result.output


def test_run_failure_exit_code():
    runner = ShellRunner(Path("/tmp"))
    m = Metric(name="fail_test", command="exit 1")
    result = runner.run(m)
    assert result.passed is False


def test_run_pattern_match():
    runner = ShellRunner(Path("/tmp"))
    m = Metric(name="pattern_test", command="echo 'Tests 42 passed'", pattern=r"Tests\s+\d+\s+passed")
    result = runner.run(m)
    assert result.passed is True


def test_run_pattern_no_match():
    runner = ShellRunner(Path("/tmp"))
    m = Metric(name="pattern_fail", command="echo 'Tests 0 failed'", pattern=r"Tests\s+\d+\s+passed")
    result = runner.run(m)
    assert result.passed is False


def test_run_timeout():
    runner = ShellRunner(Path("/tmp"), timeout=1)
    m = Metric(name="slow", command=f'"{sys.executable}" -c "import time; time.sleep(10)"')
    result = runner.run(m)
    assert result.passed is False
    assert "TIMEOUT" in result.output


def test_run_metric_specific_timeout():
    runner = ShellRunner(Path("/tmp"), timeout=5)
    m = Metric(
        name="slow",
        command=f'"{sys.executable}" -c "import time; time.sleep(2)"',
        timeout_seconds=1,
    )
    result = runner.run(m)
    assert result.passed is False
    assert "TIMEOUT (1s)" in result.output


def test_timeout_terminates_the_complete_process_tree(tmp_path, monkeypatch):
    """A timeout must delegate cleanup to the process-tree terminator."""
    process = type("Process", (), {"pid": 12345, "returncode": None})()

    def communicate(timeout=None):
        if timeout is not None:
            raise subprocess.TimeoutExpired("slow-command", timeout)
        return "", ""

    process.communicate = communicate
    process.kill = lambda: None
    terminated = []
    monkeypatch.setattr(shell_module.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        shell_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("slow-command", 1)),
    )
    monkeypatch.setattr(
        shell_module,
        "_terminate_process_tree",
        lambda candidate: terminated.append(candidate),
        raising=False,
    )
    runner = ShellRunner(tmp_path, timeout=1)

    result = runner.run(Metric(name="slow", command="slow-command"))

    assert result.passed is False
    assert "TIMEOUT" in result.output
    assert terminated == [process]


def test_process_tree_termination_targets_group_after_parent_exits(monkeypatch):
    """A child holding inherited pipes must be killed even after its shell exits."""
    process = type("Process", (), {"pid": 12345})()
    process.kill = lambda: None
    terminated = []
    monkeypatch.setattr(process_module.os, "name", "posix")
    monkeypatch.setattr(
        process_module.os,
        "killpg",
        lambda pid, signal: terminated.append((pid, signal)),
        raising=False,
    )

    process_module.terminate_process_tree(process)

    assert terminated
    assert terminated[0][0] == process.pid


def test_run_hard_gate_preserved():
    runner = ShellRunner(Path("/tmp"))
    m = Metric(name="gate", command="echo ok", hard_gate=True)
    result = runner.run(m)
    assert result.hard_gate is True


def test_run_batch_serial():
    runner = ShellRunner(Path("/tmp"))
    metrics = [
        Metric(name="a", command="echo a"),
        Metric(name="b", command="echo b"),
    ]
    results = runner.run_batch(metrics)
    assert len(results) == 2
    assert results[0].metric_name == "a"
    assert results[1].metric_name == "b"


def test_run_batch_parallel():
    runner = ShellRunner(Path("/tmp"))
    metrics = [
        Metric(name="a", command="echo a"),
        Metric(name="b", command="echo b"),
    ]
    results = runner.run_batch(metrics, parallel=True)
    assert len(results) == 2
    # Order preserved
    assert results[0].metric_name == "a"
    assert results[1].metric_name == "b"


def test_run_batch_parallel_uses_requested_worker_limit(monkeypatch):
    captured: list[int] = []

    class CapturingExecutor:
        def __init__(self, max_workers: int) -> None:
            captured.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def submit(self, func, *args):
            future = Future()
            future.set_result(func(*args))
            return future

    monkeypatch.setattr(shell_module, "ThreadPoolExecutor", CapturingExecutor)
    runner = ShellRunner(Path("/tmp"))
    metrics = [Metric(name="a", command="echo a"), Metric(name="b", command="echo b")]

    results = runner.run_batch(metrics, parallel=True, max_workers=2)

    assert [result.metric_name for result in results] == ["a", "b"]
    assert captured == [2]


def test_run_batch_dry_run():
    runner = ShellRunner(Path("/tmp"))
    metrics = [Metric(name="x", command="rm -rf /")]
    results = runner.run_batch(metrics, dry_run=True)
    assert results[0].passed is True
    assert "[DRY-RUN]" in results[0].output


def test_run_batch_emits_progress_events():
    runner = ShellRunner(Path("/tmp"))
    metrics = [Metric(name="a", command="echo a"), Metric(name="b", command="echo b")]
    events: list[tuple[str, str, str | None]] = []

    def capture(event: str, metric: Metric, result) -> None:
        events.append((event, metric.name, None if result is None else result.state.value))

    runner.run_batch(metrics, progress_callback=capture)

    assert events == [
        ("start", "a", None),
        ("end", "a", "pass"),
        ("start", "b", None),
        ("end", "b", "pass"),
    ]


def test_run_streams_output_lines_to_callback():
    emitted: list[tuple[str, str, str]] = []
    runner = ShellRunner(
        Path("/tmp"),
        stream_output=True,
        output_callback=lambda metric, source, line: emitted.append((metric.name, source, line.strip())),
    )
    metric = Metric(
        name="streamed",
        command=f'"{sys.executable}" -c "import sys; print(\'hello\'); print(\'oops\', file=sys.stderr)"',
    )

    result = runner.run(metric)

    assert result.passed is True
    assert "hello" in result.output
    assert "oops" in result.output
    assert ("streamed", "stdout", "hello") in emitted
    assert ("streamed", "stderr", "oops") in emitted


def test_streaming_runner_decodes_utf8_output_on_windows(tmp_path):
    """UTF-8 subprocess output must not depend on the Windows ANSI code page."""
    runner = ShellRunner(tmp_path, stream_output=True, output_callback=lambda *_args: None)
    metric = Metric(
        name="utf8_output",
        command=(
            f'"{sys.executable}" -c "import sys; '
            "sys.stdout.buffer.write('Entrix 可执行质量门禁\\n'.encode('utf-8'))\""
        ),
    )

    result = runner.run(metric)

    assert result.passed is True
    assert "Entrix 可执行质量门禁" in result.output


def test_run_waived_metric():
    runner = ShellRunner(Path("/tmp"))
    metric = Metric(
        name="waived",
        command="exit 1",
        waiver=Waiver(reason="temporary waiver", expires_at=date.today() + timedelta(days=1)),
    )
    result = runner.run(metric)
    assert result.passed is True


# === Fix 1: ANSI escape codes don't cause false failures ===

def test_run_pattern_match_with_ansi_codes():
    """Pattern matching should work correctly even when output contains ANSI color codes."""
    runner = ShellRunner(Path("/tmp"))
    m = Metric(
        name="ansi_test",
        command=(
            f'"{sys.executable}" -c "print(chr(27)+\'[1m\'+chr(27)+\'[32mTests  1236 '
            "passed'+chr(27)+'[39m'+chr(27)+'[22m', end='')\""
        ),
        pattern=r"Tests\s+\d+\s+passed",
    )
    result = runner.run(m)
    assert result.passed is True
    assert result.state == ResultState.PASS


# === Fix 1: Exit-code-first hybrid judgment ===

def test_run_pattern_exit_code_nonzero_overrides_pattern():
    """Even if the pattern is found, a non-zero exit code means failure."""
    runner = ShellRunner(Path("/tmp"))
    m = Metric(
        name="exit_override",
        command="echo 'Tests 42 passed' && exit 1",
        pattern=r"Tests\s+\d+\s+passed",
    )
    result = runner.run(m)
    assert result.passed is False


# === Fix 2: Output stored with ANSI stripped ===

def test_output_is_ansi_stripped():
    """Stored output should have ANSI codes removed for clean display."""
    runner = ShellRunner(Path("/tmp"))
    m = Metric(
        name="ansi_strip",
        command=f'"{sys.executable}" -c "print(chr(27)+\'[31mred text\'+chr(27)+\'[0m\', end=\'\')"',
    )
    result = runner.run(m)
    assert "\x1b" not in result.output
    assert "red text" in result.output


# === Fix 2: Smart truncation keeps head and tail ===

def test_output_smart_truncation_preserves_tail():
    """Long output should keep both head and tail, not just first N chars."""
    runner = ShellRunner(Path("/tmp"))
    # Generate output with a distinctive marker at the end
    m = Metric(
        name="truncation_test",
        command=(
            f'"{sys.executable}" -c "[print(\'filler line\', i) for i in range(500)]; '
            "print('FINAL_VERDICT: ok')\""
        ),
    )
    result = runner.run(m)
    # The tail should be preserved
    assert "FINAL_VERDICT: ok" in result.output


# === Fix 5: returncode is stored on MetricResult ===

def test_result_stores_returncode():
    """MetricResult should store the process exit code."""
    runner = ShellRunner(Path("/tmp"))
    m = Metric(name="rc_test", command="exit 42")
    result = runner.run(m)
    assert result.returncode == 42
    assert result.passed is False


# === Fix 6: Distinguish checker infra errors ===

def test_infra_error_when_both_exit_and_pattern_fail():
    """When exit code != 0 AND pattern not found, result should be UNKNOWN (infra error)."""
    runner = ShellRunner(Path("/tmp"))
    m = Metric(
        name="infra_fail",
        command="echo 'ENOENT: no such file' && exit 1",
        pattern=r"Tests\s+\d+\s+passed",
    )
    result = runner.run(m)
    assert result.passed is False
    assert result.state == ResultState.UNKNOWN
    assert result.is_infra_error is True


def test_product_failure_when_exit_ok_but_pattern_fails():
    """When exit code is 0 but pattern not found, it's a real failure (not infra)."""
    runner = ShellRunner(Path("/tmp"))
    m = Metric(
        name="product_fail",
        command="echo 'Tests 0 failed'",
        pattern=r"Tests\s+\d+\s+passed",
    )
    result = runner.run(m)
    assert result.passed is False
    assert result.state == ResultState.FAIL
    assert result.is_infra_error is False
