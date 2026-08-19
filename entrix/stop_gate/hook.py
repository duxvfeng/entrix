"""Claude Code Stop hook 入口 —— 将 Stop Gate 接入插件生命周期。

契约（Claude Code Stop hook，command 类型）：

- 输入：stdin 收到 JSON 载荷，包含 ``session_id``、``transcript_path``、
  ``cwd``、``hook_event_name``、``stop_hook_active`` 等字段。
- 放行：退出码 0 且不产生 stdout。
- 阻断：退出码 0，stdout 输出 ``{"decision": "block", "reason": "..."}``，
  ``reason`` 会回传给 Claude 使其继续修复。
- ``stop_hook_active`` 为真时也必须保留门禁：相同工作区快照重用上次
  裁决，工作区变更后重新收集证据。

安全阀：

- 环境变量 ``ENTRIX_STOP_GATE_DISABLED`` 非空时直接放行。
- 工作区没有 ``harness.yaml`` 的仓库不激活门禁，直接放行，
  这样插件可以全局安装而不影响未配置的仓库。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import IO, Any

import yaml

from entrix.stop_gate.feedback import format_block_feedback
from entrix.stop_gate.revalidation import CachedVerdict, StopGateStateStore
from entrix.stop_gate.phase import consume_phase, read_phase

DEFAULT_TIMEOUT_SECONDS = 240

BLOCK_DECISION = "block"

_FINGERPRINT_IGNORED_DIRECTORIES = frozenset(
    {
        ".claude",
        ".git",
        ".gradle",
        ".harness",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "build",
        "node_modules",
        "out",
        "target",
        "venv",
    }
)


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


def derive_changed_files(workspace: Path) -> list[str] | None:
    """从 git 工作区状态推导本次会话的变更文件列表。

    非 git 仓库或 git 不可用时返回 ``None``，由调用方进入完整检查，
    避免把无法确认变更状态误判为干净工作区。
    """
    try:
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if git_root.returncode != 0:
            return None
        discovered_root = Path(git_root.stdout.strip()).resolve()
        # A pytest temporary directory nested inside this checkout is not the
        # checkout itself. Do not mistake the clean parent status for its own.
        if discovered_root != workspace.resolve():
            return None
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

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


def has_code_change(changed_files: list[str]) -> bool:
    """判断是否有代码变更（需要质量检查）。

    规则：
    1. 修改了源代码文件（src/, lib/, *.py, *.js 等）-> 需要检查
    2. 修改了配置文件（pyproject.toml, package.json 等）-> 需要检查
    3. 修改了测试文件 -> 需要检查
    4. 只修改文档（docs/, README, CHANGELOG 等）-> 不检查

    Args:
        changed_files: 本次会话变更的文件列表

    Returns:
        True 如果有代码变更需要检查，False 如果只是文档变更
    """
    if not changed_files:
        return False

    # 源代码目录/后缀
    SOURCE_PATTERNS = {
        "src/", "lib/", "app/", "entrix/", "packages/",
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".java", ".go", ".rs", ".cpp", ".c", ".h",
        ".sh", ".yml", ".yaml"
    }

    # 配置文件
    CONFIG_FILES = {
        "pyproject.toml", "package.json", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle",
        "harness.yaml", ".github", "Makefile",
        "dockerfile", ".dockerignore"
    }

    # 测试目录
    TEST_PATTERNS = {
        "tests/", "test/", "__tests__", ".test."
    }

    for file_path in changed_files:
        # 转小写便于匹配
        path_lower = file_path.lower()

        # 检查是否是配置文件
        if any(config in file_path for config in CONFIG_FILES):
            return True

        # 检查是否是测试文件
        if any(test in path_lower for test in TEST_PATTERNS):
            return True

        # 检查是否是源代码
        if (any(src in path_lower for src in SOURCE_PATTERNS) or
            any(file_path.endswith(ext) for ext in SOURCE_PATTERNS)):
            return True

    # 没有代码变更
    return False


def workspace_fingerprint(workspace: Path) -> str | None:
    """Return a content-aware snapshot of the Git worktree."""
    try:
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if git_root.returncode != 0:
            return _filesystem_fingerprint(workspace)
        discovered_root = Path(git_root.stdout.strip()).resolve()
        if discovered_root != workspace.resolve():
            return _filesystem_fingerprint(workspace)

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        changed = subprocess.run(
            ["git", "diff", "--name-only", "-z", "HEAD"],
            cwd=workspace,
            capture_output=True,
            timeout=10,
            check=False,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=workspace,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _filesystem_fingerprint(workspace)
    if any(result.returncode != 0 for result in (head, status, changed, untracked)):
        return _filesystem_fingerprint(workspace)

    changed_paths = {
        path.decode("utf-8", errors="surrogateescape")
        for path in changed.stdout.split(b"\0")
        if path
    }
    changed_paths.update(
        path.decode("utf-8", errors="surrogateescape")
        for path in untracked.stdout.split(b"\0")
        if path
    )
    digest = hashlib.sha256()
    digest.update(head.stdout.strip().encode("utf-8", errors="surrogateescape"))
    digest.update(status.stdout.encode("utf-8", errors="surrogateescape"))
    for relative_path in sorted(changed_paths):
        digest.update(relative_path.encode("utf-8", errors="surrogateescape"))
        candidate = workspace / relative_path
        try:
            with candidate.open("rb") as file:
                while chunk := file.read(1024 * 1024):
                    digest.update(chunk)
        except FileNotFoundError:
            digest.update(b"<missing>")
        except OSError:
            return None
    for config_path in (workspace / "harness.yaml", workspace / ".harness" / "harness.yaml"):
        digest.update(str(config_path.relative_to(workspace)).encode("utf-8"))
        try:
            with config_path.open("rb") as file:
                while chunk := file.read(1024 * 1024):
                    digest.update(chunk)
        except FileNotFoundError:
            digest.update(b"<missing>")
        except OSError:
            return None
    return digest.hexdigest()


def _filesystem_fingerprint(workspace: Path) -> str | None:
    """Return a cheap fallback snapshot for configured non-Git workspaces."""
    digest = hashlib.sha256(b"filesystem-fingerprint/v1\0")
    try:
        for root, directories, filenames in os.walk(workspace):
            directories[:] = sorted(
                directory
                for directory in directories
                if directory not in _FINGERPRINT_IGNORED_DIRECTORIES
            )
            for filename in sorted(filenames):
                candidate = Path(root) / filename
                relative_path = candidate.relative_to(workspace)
                stat = candidate.stat()
                digest.update(str(relative_path).encode("utf-8", errors="surrogateescape"))
                digest.update(str(stat.st_size).encode("ascii"))
                digest.update(str(stat.st_mtime_ns).encode("ascii"))
        for config_path in (workspace / "harness.yaml", workspace / ".harness" / "harness.yaml"):
            try:
                stat = config_path.stat()
            except FileNotFoundError:
                continue
            digest.update(str(config_path.relative_to(workspace)).encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
    except OSError:
        return None
    return digest.hexdigest()


def _gate_fingerprint(
    workspace_snapshot: str | None,
    branch: str,
    base_ref: str,
    environment_snapshot: str,
) -> str | None:
    """Bind a workspace snapshot to every input that can alter Harness evidence."""
    if workspace_snapshot is None:
        return None
    payload = "\0".join((workspace_snapshot, branch, base_ref, environment_snapshot))
    return hashlib.sha256(payload.encode("utf-8", errors="surrogateescape")).hexdigest()


def _when_environment_fingerprint(config_path: Path) -> str:
    """Return the configured environment inputs that can activate Harness checks."""
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ""
    if not isinstance(config, dict):
        return ""

    conditions = [config.get("when")]
    producers = config.get("evidence_producers")
    if isinstance(producers, list):
        conditions.extend(
            producer.get("when") for producer in producers if isinstance(producer, dict)
        )
    gates = config.get("gate_policies")
    if isinstance(gates, list):
        conditions.extend(gate.get("when") for gate in gates if isinstance(gate, dict))

    names: set[str] = set()
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        required_variables = condition.get("env")
        if isinstance(required_variables, dict):
            names.update(name for name in required_variables if isinstance(name, str))

    payload = "\0".join(f"{name}={os.environ.get(name)!r}" for name in sorted(names))
    return hashlib.sha256(payload.encode("utf-8", errors="surrogateescape")).hexdigest()


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
    state_dir: Path | None = None,
) -> int:
    """执行 Stop hook 主流程，返回进程退出码。

    该函数是 ``entrix stop-gate`` 的核心：读取 Claude Code 载荷，
    必要时运行 Stop Gate 裁决，并按 hook 契约输出决策。
    """
    if output_stream is None:
        output_stream = sys.stdout

    # 安全阀：显式禁用时放行
    if os.environ.get("ENTRIX_STOP_GATE_DISABLED"):
        print(
            "ENTRIX_STOP_GATE_DISABLED is set; Harness Stop Gate is bypassed.",
            file=sys.stderr,
        )
        return 0

    payload = read_hook_payload(input_stream)
    workspace = Path(payload.get("cwd") or os.getcwd()).resolve()
    harness_config = find_harness_config(workspace)
    if harness_config is None:
        return 0
    try:
        phase = read_phase(workspace)
        if consume_phase(workspace, "init") or phase == "planning":
            return 0
        detected_changed_files = derive_changed_files(workspace)
        changed_files = detected_changed_files or []
        detection_failed = detected_changed_files is None

        # 🎯 只有代码变更才触发 Stop Gate 检查
        if not detection_failed and not has_code_change(changed_files):
            print(
                f"[Entrix] 未检测到代码变更（仅: {', '.join(changed_files[:3]) if changed_files else '无变更'}{'...' if len(changed_files) > 3 else ''}），跳过 Stop Gate 检查",
                file=sys.stderr,
            )
            return 0

        should_collect = phase == "implementation" or bool(changed_files) or detection_failed

        session_id = str(payload.get("session_id") or "unknown-session")
        stop_reason = str(payload.get("reason") or "agent_completed")
        branch = str(payload.get("branch") or derive_current_branch(workspace))
        return _run_configured_stop_gate(
            workspace=workspace,
            session_id=session_id,
            stop_reason=stop_reason,
            branch=branch,
            base_ref=base_ref,
            harness_config=harness_config,
            changed_files=changed_files,
            should_collect=should_collect,
            output_stream=output_stream,
            state_dir=state_dir,
        )
    except Exception as error:  # noqa: BLE001
        _write_block_decision(output_stream, f"Harness 执行失败：{error}")
        return 0


def _run_configured_stop_gate(
    *,
    workspace: Path,
    session_id: str,
    stop_reason: str,
    branch: str,
    base_ref: str | None,
    harness_config: Path,
    changed_files: list[str],
    should_collect: bool,
    output_stream: IO[str],
    state_dir: Path | None,
) -> int:
    """Run the configured fail-closed path after Harness discovery."""
    effective_base_ref = str(base_ref or "HEAD")
    snapshot = _gate_fingerprint(
        workspace_fingerprint(workspace),
        branch,
        effective_base_ref,
        _when_environment_fingerprint(harness_config),
    )
    state_store = StopGateStateStore(state_dir)
    cached = state_store.load(workspace, session_id) if snapshot is not None else None
    if cached is not None and cached.fingerprint == snapshot:
        if cached.status in {"fail", "blocked", "error"}:
            _write_block_decision(
                output_stream,
                "上次 Harness 验证未通过，且未检测到代码变更；未重新运行测试。"
                f"原始原因：{cached.summary}",
            )
            return 0
        state_store.delete(workspace, session_id)

    if not should_collect:
        return 0

    context = {
        "session_id": session_id,
        "task_id": session_id,
        "workspace": workspace,
        "changed_files": changed_files,
        "branch": branch,
        "stop_reason": stop_reason,
        "base_ref": base_ref,
    }

    from entrix.stop_gate.runner import HarnessRunner

    try:
        result = HarnessRunner(
            harness_config,
            evidence_root=state_store.evidence_root(workspace),
        ).run(context)
    except Exception as error:  # noqa: BLE001
        summary = f"Harness 执行失败：{error}"
        _save_cached_verdict(state_store, workspace, session_id, snapshot, "error", summary)
        _write_block_decision(output_stream, summary)
        return 0

    verdict = result.verdict
    status = str(getattr(verdict.status, "value", verdict.status))
    summary = verdict.summary or "Harness 门禁未通过。"
    _save_cached_verdict(state_store, workspace, session_id, snapshot, status, summary)
    if status == "pass":
        return 0
    if result.bundle is not None:
        feedback = format_block_feedback(
            verdict,
            result.bundle,
            bundle_path=result.bundle_path,
            attempt_id=str(context.get("attempt_id") or session_id),
        )
        _write_block_decision(output_stream, feedback.reason, feedback.to_dict())
    else:
        _write_block_decision(output_stream, summary)
    return 0


def _save_cached_verdict(
    state_store: StopGateStateStore,
    workspace: Path,
    session_id: str,
    fingerprint: str | None,
    status: str,
    summary: str,
) -> None:
    if status == "pass":
        try:
            state_store.delete(workspace, session_id)
        except OSError:
            pass
        return
    if fingerprint is None:
        return
    try:
        state_store.save(
            workspace,
            session_id,
            CachedVerdict(fingerprint=fingerprint, status=status, summary=summary),
        )
    except OSError:
        return


def _write_block_decision(output_stream: IO[str], reason: str, details: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"decision": BLOCK_DECISION, "reason": reason}
    if details:
        payload.update(details)
    json.dump(payload, output_stream, ensure_ascii=False)
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
        summary = f"Harness Stop Gate 内部错误：{e}"
        try:
            configured = find_harness_config(Path.cwd().resolve()) is not None
        except OSError:
            configured = False
        if configured:
            _write_block_decision(sys.stdout, summary)
        else:
            print(f"entrix stop-gate: {summary}", file=sys.stderr)
        return 0
