"""Cross-platform subprocess lifecycle and shared shell execution helpers."""

from __future__ import annotations

import os
import re
import signal
import subprocess
from dataclasses import dataclass
from os import environ
from pathlib import Path
from time import monotonic
from typing import Any

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")

# 保留前 4KB 和后 4KB，这样启动上下文和最终的
# 摘要（通过/失败行）在截断后仍然可见。
_OUTPUT_HEAD = 4000
_OUTPUT_TAIL = 4000
_OUTPUT_MAX = _OUTPUT_HEAD + _OUTPUT_TAIL + 200  # a bit of slack


def smart_truncate(text: str) -> str:
    """保留输出的头部和尾部，使上下文和判定结果都可见。"""
    if len(text) <= _OUTPUT_MAX:
        return text
    head = text[:_OUTPUT_HEAD]
    tail = text[-_OUTPUT_TAIL:]
    omitted = len(text) - _OUTPUT_HEAD - _OUTPUT_TAIL
    return f"{head}\n\n... [{omitted} characters omitted] ...\n\n{tail}"


def strip_ansi(text: str) -> str:
    """移除 ANSI 转义序列，便于 pattern 匹配与存储。"""
    return _ANSI_ESCAPE.sub("", text)


@dataclass
class ShellCommandOutcome:
    """Uniform result of a captured shell command execution."""

    stdout: str
    stderr: str
    returncode: int
    duration_ms: float
    timed_out: bool


def shell_command_parts(command: str) -> tuple[str | list[str], bool]:
    """Pick the platform-appropriate shell invocation for a command string."""
    if os.name == "nt":
        return command, True
    return ["/bin/bash", "-lc", command], False


def run_shell_command(
    command: str,
    *,
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> ShellCommandOutcome:
    """Execute a command string with uniform shell, env, timeout and cleanup.

    ShellRunner 与 CommandProducer 的共享底层执行路径：统一平台 shell 选择、
    UTF-8 解码、env 合并、进程组创建与超时进程树终止。
    """
    resolved_command, use_shell = shell_command_parts(command)
    process = subprocess.Popen(
        resolved_command,
        shell=use_shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env={**environ, **(env_overrides or {})},
        **process_group_kwargs(),
    )
    start = monotonic()
    timed_out = False
    stdout: str | None = ""
    stderr: str | None = ""
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                stdout, stderr = process.communicate()
            except (subprocess.TimeoutExpired, OSError, ValueError):
                stdout, stderr = "", ""
    return ShellCommandOutcome(
        stdout=stdout or "",
        stderr=stderr or "",
        returncode=process.returncode if process.returncode is not None else -1,
        duration_ms=(monotonic() - start) * 1000,
        timed_out=timed_out,
    )


def process_group_kwargs() -> dict[str, Any]:
    """Start a subprocess in a group that can be terminated with its children."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def terminate_process_tree(process: subprocess.Popen) -> None:
    """Terminate a command and all descendants after a timeout."""
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            process.kill()
        else:
            if result.returncode != 0:
                for child_pid in _windows_child_pids(process.pid):
                    subprocess.run(
                        ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                process.kill()
        return
    kill_process_group = getattr(os, "killpg", None)
    if kill_process_group is None:
        process.kill()
        return
    try:
        kill_process_group(process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except ProcessLookupError:
        pass


def _windows_child_pids(parent_pid: int) -> list[int]:
    """Return direct children when the original shell has already exited."""
    command = (
        "$ErrorActionPreference='Stop'; "
        f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId = {parent_pid}').ProcessId"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    child_pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            child_pids.append(int(line.strip()))
        except ValueError:
            continue
    return child_pids
