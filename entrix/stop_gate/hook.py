"""Claude Code Stop hook 入口 —— 将 Stop Gate 接入插件生命周期。

契约（Claude Code Stop hook，command 类型）：

- 输入：stdin 收到 JSON 载荷，包含 ``session_id``、``transcript_path``、
  ``cwd``、``hook_event_name``、``stop_hook_active`` 等字段。
- 放行：退出码 0 且不产生 stdout。
- 阻断：退出码 0，stdout 输出 ``{"decision": "block", "reason": "..."}``，
  ``reason`` 会回传给 Claude 使其继续修复。
- ``stop_hook_active`` 为真时直接放行，避免 Claude 在 Stop hook 重试时
  进入无限阻断循环。

安全阀：

- 环境变量 ``ENTRIX_STOP_GATE_DISABLED`` 解析为显式 true 值时直接放行。
- 工作区没有 ``harness.yaml`` 的仓库不激活门禁，直接放行，
  这样插件可以全局安装而不影响未配置的仓库。
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import IO, Any

import yaml

from entrix.harness.config import HARNESS_CONFIG_CANDIDATES
from entrix.stop_gate.feedback import format_block_feedback
from entrix.stop_gate.phase import consume_phase, read_phase
from entrix.stop_gate.revalidation import CachedVerdict, StopGateStateStore

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


def _stop_gate_disabled() -> bool:
    """Return whether the explicit Stop Gate bypass switch is enabled."""
    value = os.environ.get("ENTRIX_STOP_GATE_DISABLED", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def find_harness_config(workspace: Path) -> Path | None:
    """Return the preferred Harness configuration file, if the workspace has one."""
    from entrix.harness.config import find_harness_config as _find_config

    return _find_config(workspace)


def read_hook_payload(stream: IO[str] | None = None) -> dict[str, Any] | None:
    """读取并解析 stdin 的 hook 载荷，无效或缺失时返回 ``None``。"""
    if stream is None:
        stream = sys.stdin
    try:
        data = stream.read()
    except OSError:
        return None
    if not data.strip():
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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


_SOURCE_DIRS = frozenset(
    {"src", "lib", "app", "entrix", "packages", "tests", "test", "__tests__", ".github"}
)
_SOURCE_EXTS = (
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".cpp", ".c", ".h",
    ".sh", ".mjs", ".ps1", ".bat", ".yml", ".yaml",
    ".json",
)
_CONFIG_BASENAMES = frozenset(
    {
        "pyproject.toml", "package.json", "cargo.toml",
        "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
        "harness.yaml", "makefile", "dockerfile", ".dockerignore",
    }
)


def has_code_change(changed_files: list[str]) -> bool:
    """判断是否有代码变更（需要质量检查）。

    规则（按 git status 的 POSIX 风格路径做结构化匹配，
    避免旧 substring 匹配对 ``myproject.toml.bak`` 之类路径的误报）：

    1. basename 精确命中配置文件（pyproject.toml、package.json 等）
    2. 路径首段为 .github 目录
    3. 文件名以源码后缀结尾（*.py、*.json 等）
    4. 路径首段位于源码或测试目录（src/、tests/ 等）
    5. 文件名 stem 的点分段包含 "test"（如 test_x.py 以外的 foo.test.ts）

    只修改文档（docs/、README、CHANGELOG 等）不触发检查。
    """
    for raw_path in changed_files:
        if not raw_path:
            continue
        path = PurePosixPath(raw_path.strip().strip('"'))
        name = path.name.lower()
        first_part = path.parts[0].lower() if path.parts else ""

        if name in _CONFIG_BASENAMES or first_part == ".github":
            return True
        if name.endswith(_SOURCE_EXTS):
            return True
        if first_part in _SOURCE_DIRS:
            return True
        if "test" in path.stem.lower().split("."):
            return True
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
    for config_path in (workspace / candidate for candidate in HARNESS_CONFIG_CANDIDATES):
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
        for config_path in (workspace / candidate for candidate in HARNESS_CONFIG_CANDIDATES):
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
    # 命令执行环境可能依赖未显式声明的运行时维度（解释器版本、工具链 PATH、
    # entrix 版本）。纳入 fingerprint 避免环境变化后复用旧的 FAIL/BLOCKED 缓存。
    runtime_parts = (
        os.name,
        sys.platform,
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        _entrix_package_version(),
        os.environ.get("PATH", ""),
    )
    payload = "\0".join((payload, *runtime_parts))
    return hashlib.sha256(payload.encode("utf-8", errors="surrogateescape")).hexdigest()


def _entrix_package_version() -> str:
    """Return the installed entrix version, or ``unknown`` when unavailable."""
    try:
        return importlib.metadata.version("entrix")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def derive_current_branch(workspace: Path, *, timeout: float = 10.0) -> str:
    """Return the checked-out branch name, or ``unknown`` outside a repository."""
    from entrix.gitinfo import current_branch

    return current_branch(workspace, timeout=timeout)


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

    stop_deadline = monotonic() + max(0.1, float(timeout_seconds))

    # 安全阀：显式禁用时放行
    if _stop_gate_disabled():
        print(
            "ENTRIX_STOP_GATE_DISABLED is set; Harness Stop Gate is bypassed.",
            file=sys.stderr,
        )
        return 0

    payload = read_hook_payload(input_stream)
    if payload is None:
        _write_block_decision(
            output_stream,
            "Stop hook 载荷无效或缺失，无法确认工作区；已按 fail-closed 阻断。",
        )
        return 0
    # Claude sets this flag when it is already continuing because a Stop hook
    # blocked the previous turn. Blocking again would create an infinite loop.
    if payload.get("stop_hook_active") is True:
        return 0

    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        _write_block_decision(
            output_stream,
            "Stop hook 载荷缺少有效 cwd，无法确认工作区；已按 fail-closed 阻断。",
        )
        return 0
    try:
        workspace = Path(cwd).resolve()
        if not workspace.is_dir():
            raise ValueError("cwd is not an existing directory")
    except (OSError, RuntimeError, ValueError) as error:
        _write_block_decision(
            output_stream,
            f"Stop hook 载荷包含无效 cwd（{error}），已按 fail-closed 阻断。",
        )
        return 0
    harness_config = find_harness_config(workspace)
    if harness_config is None:
        return 0

    try:
        session_id = str(payload.get("session_id") or "unknown-session")
        stop_reason = str(payload.get("reason") or "agent_completed")
        phase = read_phase(workspace, session_id=session_id) or read_phase(workspace)
        if (
            consume_phase(workspace, "init", session_id=session_id)
            or consume_phase(workspace, "init")
            or phase == "planning"
        ):
            return 0
        detected_changed_files = derive_changed_files(workspace)
        changed_files = detected_changed_files or []
        detection_failed = detected_changed_files is None

        # 提前计算session_id和branch，以便缓存检查
        try:
            branch = str(payload.get("branch") or derive_current_branch(workspace))
        except Exception as error:
            # 分支检测失败时，输出 block 决策
            print(f"[Entrix] 分支检测失败: {error}", file=sys.stderr)
            _write_block_decision(output_stream, f"分支检测不可用：{error}")
            return 0

        # 计算fingerprint以便缓存检查
        effective_base_ref = str(base_ref or "HEAD")
        snapshot = _gate_fingerprint(
            workspace_fingerprint(workspace),
            branch,
            effective_base_ref,
            _when_environment_fingerprint(harness_config),
        )
        state_store = StopGateStateStore(state_dir)
        try:
            cached = state_store.load(workspace, session_id) if snapshot is not None else None
        except Exception as error:
            # 状态存储加载失败时，输出 block 决策
            print(f"[Entrix] 状态存储加载失败: {error}", file=sys.stderr)
            _write_block_decision(output_stream, f"状态存储不可用：{error}")
            return 0
        if cached is not None and cached.fingerprint == snapshot:
            if cached.status in {"fail", "blocked", "error"}:
                # 清理错误状态，给重新运行的机会
                if cached.status == "error":
                    print("[Entrix] 清理之前的错误状态", file=sys.stderr)
                    state_store.delete(workspace, session_id)
                    # 继续运行检查
                else:
                    _write_block_decision(
                        output_stream,
                        "上次 Harness 验证未通过，且未检测到代码变更；未重新运行测试。"
                        f"原始原因：{cached.summary}",
                    )
                    return 0
            state_store.delete(workspace, session_id)

        # 🎯 只有代码变更才触发 Stop Gate 检查（除了 implementation 阶段）
        if not detection_failed and not has_code_change(changed_files) and phase != "implementation":
            print(
                f"[Entrix] 未检测到代码变更（仅: {', '.join(changed_files[:3]) if changed_files else '无变更'}{'...' if len(changed_files) > 3 else ''}），跳过 Stop Gate 检查",
                file=sys.stderr,
            )
            return 0

        should_collect = phase == "implementation" or bool(changed_files) or detection_failed

        if should_collect and not state_store.is_config_trusted(workspace, harness_config):
            _write_block_decision(
                output_stream,
                "发现尚未信任的 Harness 配置；为避免自动执行不可信命令，Stop Gate 已暂停。"
                f"请先检查 {harness_config}，确认后运行 `entrix trust --repo {workspace}`。",
            )
            return 0

        return _run_configured_stop_gate(
            workspace=workspace,
            session_id=session_id,
            stop_reason=stop_reason,
            branch=branch,
            base_ref=base_ref,
            harness_config=harness_config,
            changed_files=changed_files,
            should_collect=should_collect,
            stop_deadline=stop_deadline,
            output_stream=output_stream,
            state_dir=state_dir,
            snapshot=snapshot or "",
            state_store=state_store,
        )
    except Exception as error:  # noqa: BLE001
        # 输出详细错误信息到 stderr，便于调试
        import traceback
        print(f"[Entrix] Stop Gate 执行异常: {error}", file=sys.stderr)
        print(f"[Entrix] 错误类型: {type(error).__name__}", file=sys.stderr)
        if os.environ.get("ENTRIX_DEBUG"):
            traceback.print_exc(file=sys.stderr)

        # A configured workspace must fail closed. Only the explicit disable
        # switch and the no-config path above are allowed to bypass the gate.
        _write_block_decision(output_stream, f"Stop Gate 执行异常，已阻断：{error}")
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
    stop_deadline: float,
    output_stream: IO[str],
    state_dir: Path | None,
    snapshot: str,
    state_store: Any,
) -> int:
    """Run the configured fail-closed path after Harness discovery."""
    # 缓存检查已在主函数中完成，直接运行检查
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
        remaining = stop_deadline - monotonic()
        if remaining <= 0:
            _write_block_decision(output_stream, "Stop Gate 总超时已到期，未完成证据收集。")
            return 0
        result = HarnessRunner(
            harness_config,
            evidence_root=state_store.evidence_root(workspace),
            timeout_seconds=remaining,
        ).run(context)
    except Exception as error:  # noqa: BLE001
        # 输出详细错误信息
        import traceback
        print(f"[Entrix] Harness 执行异常: {error}", file=sys.stderr)
        if os.environ.get("ENTRIX_DEBUG"):
            traceback.print_exc(file=sys.stderr)

        # 异常时输出 block 决策
        summary = f"Harness 执行失败：{error}"
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
