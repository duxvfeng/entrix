"""Claude Code Stop hook 入口 —— 将 Stop Gate 接入插件生命周期。

契约（Claude Code Stop hook，command 类型）：

- 输入：stdin 收到 JSON 载荷，包含 ``session_id``、``transcript_path``、
  ``cwd``、``hook_event_name``、``stop_hook_active`` 等字段。
- 放行：退出码 0 且不产生 stdout。
- 阻断：退出码 0，stdout 输出 ``{"decision": "block", "reason": "..."}``，
  ``reason`` 会回传给 Claude 使其继续修复。
- ``stop_hook_active`` 为真表示 Claude 已因 Stop hook 继续工作，
  必须立即放行以避免无限循环。

安全阀：

- 环境变量 ``ENTRIX_STOP_GATE_DISABLED`` 非空时直接放行。
- 工作区没有 ``docs/fitness/`` 规格的仓库不激活门禁，直接放行，
  这样插件可以全局安装而不影响未配置的仓库。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import IO

DEFAULT_TIMEOUT_SECONDS = 240

BLOCK_DECISION = "block"


def find_harness_config(workspace: Path) -> Path | None:
    """Return the preferred Harness configuration file, if the workspace has one."""
    for config_path in (workspace / "harness.yaml", workspace / ".harness" / "harness.yaml"):
        if config_path.is_file():
            return config_path
    return None


def read_hook_payload(stream: IO[str] | None = None) -> dict:
    """读取并解析 stdin 的 hook 载荷，损坏或缺失时返回空 dict。"""
    if stream is None:
        stream = sys.stdin
    try:
        data = stream.read()
    except OSError:
        return {}
    if not data.strip():
        return {}
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def has_fitness_specs(workspace: Path) -> bool:
    """判断工作区是否配置了 Entrix 护栏规格。"""
    fitness_dir = workspace / "docs" / "fitness"
    if not fitness_dir.is_dir():
        return False
    if (fitness_dir / "manifest.yaml").is_file():
        return True
    return any(fitness_dir.glob("*.md"))


def derive_changed_files(workspace: Path) -> list[str]:
    """从 git 工作区状态推导本次会话的变更文件列表。

    非 git 仓库或 git 不可用时返回空列表（等价于全量检查）。
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    changed: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        # 重命名条目形如 "R  old -> new"，取新路径
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path:
            changed.append(path)
    return changed


def derive_current_branch(workspace: Path) -> str:
    """Return the checked-out branch name, or ``unknown`` outside a repository."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    branch = result.stdout.strip()
    return branch if result.returncode == 0 and branch else "unknown"


def run_stop_gate_hook(
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    base_ref: str | None = None,
    input_stream: IO[str] | None = None,
    output_stream: IO[str] | None = None,
) -> int:
    """执行 Stop hook 主流程，返回进程退出码。

    该函数是 ``entrix stop-gate`` 的核心：读取 Claude Code 载荷，
    必要时运行 Stop Gate 裁决，并按 hook 契约输出决策。
    """
    if output_stream is None:
        output_stream = sys.stdout

    # 安全阀：显式禁用时放行
    if os.environ.get("ENTRIX_STOP_GATE_DISABLED"):
        return 0

    payload = read_hook_payload(input_stream)

    # 防循环：Claude 已因 Stop hook 继续工作，必须放行
    if payload.get("stop_hook_active"):
        return 0

    workspace = Path(payload.get("cwd") or os.getcwd()).resolve()

    session_id = str(payload.get("session_id") or "unknown-session")
    stop_reason = str(payload.get("reason") or "agent_completed")
    context = {
        "session_id": session_id,
        "task_id": session_id,
        "workspace": workspace,
        "changed_files": derive_changed_files(workspace),
        "branch": str(payload.get("branch") or derive_current_branch(workspace)),
        "stop_reason": stop_reason,
        "base_ref": base_ref,
    }

    harness_config = find_harness_config(workspace)
    if harness_config is not None:
        from entrix.stop_gate.runner import HarnessRunner

        try:
            verdict = HarnessRunner(harness_config).run(context)
        except Exception as error:  # noqa: BLE001
            _write_block_decision(output_stream, f"Harness 执行失败：{error}")
            return 0

        if getattr(verdict.status, "value", verdict.status) == "pass":
            return 0
        _write_block_decision(output_stream, verdict.summary or "Harness 门禁未通过。")
        return 0

    # 未配置 Harness 且没有 legacy 规格的仓库不激活门禁
    if not has_fitness_specs(workspace):
        return 0

    # 延迟导入，避免 hook 入口对 stop_gate 子系统的硬依赖
    from entrix.stop_gate.adapter import StopGateAdapter

    adapter = StopGateAdapter(
        state_dir=workspace / ".claude" / "stop-gate",
        timeout_seconds=timeout_seconds,
    )
    decision = adapter.on_before_stop(
        context
    )

    if decision.allow_stop:
        return 0

    reason = decision.feedback or "Stop Gate 阻止了本次停止，请修复反馈中的问题后重试。"
    _write_block_decision(output_stream, reason)
    return 0


def _write_block_decision(output_stream: IO[str], reason: str) -> None:
    json.dump(
        {"decision": BLOCK_DECISION, "reason": reason},
        output_stream,
        ensure_ascii=False,
    )
    output_stream.write("\n")
    output_stream.flush()


def main(argv: list[str] | None = None) -> int:
    """``entrix stop-gate`` CLI 入口。"""
    import argparse

    env_timeout = os.environ.get("ENTRIX_STOP_GATE_TIMEOUT")
    parser = argparse.ArgumentParser(
        prog="entrix stop-gate",
        description="作为 Claude Code Stop hook 运行 Entrix 质量门禁（stdin 读取 hook 载荷）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(env_timeout) if env_timeout and env_timeout.isdigit() else DEFAULT_TIMEOUT_SECONDS,
        help="证据收集超时（秒），默认 %(default)s",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="diff 使用的 git base ref，默认让 Stop Gate 自行决定",
    )
    args = parser.parse_args(argv)

    try:
        return run_stop_gate_hook(timeout_seconds=args.timeout, base_ref=args.base)
    except Exception as e:  # noqa: BLE001
        # 基础设施级故障时放行，避免把用户会话锁死在 hook 里
        print(f"entrix stop-gate: 内部错误，放行本次停止：{e}", file=sys.stderr)
        return 0
