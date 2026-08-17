"""Cross-platform subprocess-group lifecycle helpers."""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Any


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
