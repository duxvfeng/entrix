"""CLI 入口 — 连接所有模块，功能与 fitness.py 保持一致。"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from entrix import __version__ as PACKAGE_VERSION
from entrix import cli_runtime as _cli_runtime
from entrix.cli_analysis import cmd_analyze_long_file, cmd_hook_file_length
from entrix.cli_graph import (
    cmd_graph_build,
    cmd_graph_history,
    cmd_graph_impact,
    cmd_graph_query,
    cmd_graph_review_context,
    cmd_graph_stats,
    cmd_graph_test_mapping,
    cmd_graph_test_radius,
)
from entrix.cli_hints import (
    HintingArgumentParser,
    print_next_steps,
    should_show_next_steps,
)
from entrix.cli_overview import print_command_overview, show_subgroup_help
from entrix.cli_release import cmd_release_trigger
from entrix.engine import collect_changed_files, run_fitness_report
from entrix.governance import GovernancePolicy, StreamOutputMode, enforce

# Harness system imports
from entrix.harness.config import HarnessConfig, load_harness_config
from entrix.harness.fitness import validate_weights
from entrix.harness.profiles import PROFILE_NAMES, ProfileDetectionError, resolve_profile
from entrix.harness.template import render_default_harness
from entrix.model import (
    ExecutionScope,
    Gate,
    Metric,
    MetricResult,
    ResultState,
    Tier,
)
from entrix.presets import get_project_preset
from entrix.reporters.terminal import TerminalReporter
from entrix.reporters.visual import AsciiReporter, RichLiveProgressReporter, RichReporter
from entrix.reporting import report_to_dict, write_report_output
from entrix.review_trigger import (
    collect_changed_files as collect_review_changed_files,
)
from entrix.review_trigger import (
    collect_diff_stats,
    evaluate_review_triggers,
)
from entrix.stop_gate.phase import clear_phase, read_phase, write_phase
from entrix.stop_gate.revalidation import StopGateStateStore
from entrix.stop_gate.runner import HarnessRunner


class _ShellOutputController:
    """协调 progress 输出，支持可选的 shell 日志流模式。"""

    def __init__(self, reporter: TerminalReporter, *, mode: StreamOutputMode = "off"):
        self.reporter = reporter
        self.mode = mode
        self._buffered_lines: dict[int, list[tuple[str, str]]] = {}
        self._lock = RLock()

    @property
    def should_capture_output(self) -> bool:
        return self.mode != "off"

    def handle_output(self, metric: Metric, source: str, line: str) -> None:
        if self.mode == "off":
            return
        if self.mode == "all":
            with self._lock:
                self.reporter.print_metric_output(metric_name=metric.name, source=source, line=line)
            return
        with self._lock:
            self._buffered_lines.setdefault(id(metric), []).append((source, line))

    def handle_progress(self, event: str, metric: Metric, result: MetricResult | None) -> None:
        with self._lock:
            self.reporter.print_metric_progress(
                event,
                metric_name=metric.name,
                tier=metric.tier.value,
                hard_gate=metric.gate == Gate.HARD,
                result=result,
            )
        if event != "end" or self.mode != "failures":
            return
        buffered = self._pop_buffer(metric)
        if result is None or result.state != ResultState.FAIL:
            return
        for source, line in buffered:
            with self._lock:
                self.reporter.print_metric_output(metric_name=metric.name, source=source, line=line)

    def _pop_buffer(self, metric: Metric) -> list[tuple[str, str]]:
        with self._lock:
            return self._buffered_lines.pop(id(metric), [])


def _find_project_root() -> Path:
    """从 CWD 向上遍历查找项目根目录；实现共享于 entrix.gitinfo。"""
    from entrix.gitinfo import find_project_root

    return find_project_root()


def _configure_utf8_streams() -> None:
    """Keep CLI status output encodable when launched from Windows subprocesses."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except OSError:
                continue


def _positive_int(value: str) -> int:
    """Parse a strictly positive command-line integer."""
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _runtime_root(project_root: Path) -> Path:
    """Compatibility seam for callers that isolate CLI runtime files in tests."""
    return _cli_runtime.runtime_root(project_root)


def _default_mcp_config() -> dict:
    return {
        "mcpServers": {
            "entrix": {
                "command": sys.executable,
                "args": ["-m", "entrix.cli", "serve"],
            }
        }
    }


def _marketplace_plugin_mode() -> bool:
    """Return whether this CLI is running from a Claude Marketplace plugin."""
    return bool(os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("ENTRIX_PLUGIN_MODE"))


def _merged_mcp_config(mcp_path: Path, *, force: bool = False) -> dict:
    """Merge Entrix into an existing MCP config without dropping other servers."""
    if not mcp_path.exists():
        return _default_mcp_config()
    try:
        existing = json.loads(mcp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取已有 .mcp.json：{error}") from error
    if not isinstance(existing, dict):
        raise ValueError(".mcp.json 根节点必须是对象")
    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(".mcp.json 的 mcpServers 必须是对象")
    desired = _default_mcp_config()["mcpServers"]["entrix"]
    current = servers.get("entrix")
    if current is not None and current != desired and not force:
        raise ValueError("已有 entrix MCP 配置与当前版本不同；请使用 --force 明确替换")
    servers["entrix"] = desired
    return existing


def _write_json_atomically(path: Path, payload: dict) -> None:
    """Write JSON without leaving a partially written project config."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _verify_mcp_runtime() -> tuple[bool, str]:
    """Import and construct the MCP server without opening its stdio loop."""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from entrix.server import create_server; create_server()",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0:
        return True, ""
    return False, result.stderr.strip() or f"exit code {result.returncode}"


def cmd_install(args: argparse.Namespace) -> int:
    """为 Claude Code MCP 集成写入 `.mcp.json`。"""
    target = Path(args.repo).resolve() if args.repo else Path.cwd().resolve()
    mcp_path = target / ".mcp.json"
    if _marketplace_plugin_mode():
        print("Marketplace 插件已由 plugin.json 注册 MCP；跳过写入 .mcp.json。")
        return 0
    try:
        mcp_config = _merged_mcp_config(mcp_path, force=getattr(args, "force", False))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    config_text = json.dumps(mcp_config, indent=2) + "\n"

    if args.dry_run:
        print(config_text)
        return 0

    _write_json_atomically(mcp_path, mcp_config)

    # 验证 MCP 服务
    print(f"✅ 已写入 Claude MCP 配置到 {mcp_path}")

    try:
        available, detail = _verify_mcp_runtime()
        if available:
            print("✅ MCP 服务运行时可用")
        else:
            print(f"⚠️  MCP 服务运行时不可用: {detail}")
    except Exception as e:
        print(f"⚠️  无法验证 MCP 服务: {e}")

    print("\n📝 下一步:")
    print("   1. 重启 Claude Code 以加载 MCP 配置")
    print("   2. 运行 'entrix --help' 验证命令可用性")

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a repository with MCP and single-file Harness configuration."""
    target = Path(args.repo).resolve() if args.repo else Path.cwd().resolve()
    harness_path = target / "harness.yaml"
    mcp_path = target / ".mcp.json"
    plugin_mode = _marketplace_plugin_mode()

    if harness_path.exists() and not args.force:
        print(f"Harness 配置已存在：{harness_path}；如需重建请使用 --force", file=sys.stderr)
        return 1

    requested_profile = getattr(args, "profile", "auto")
    try:
        selected_profile = resolve_profile(requested_profile, target)
        harness_text = render_default_harness(selected_profile, target)
    except (ProfileDetectionError, ValueError) as error:
        print(f"无法初始化 Harness：{error}", file=sys.stderr)
        return 1

    mcp_config = None
    if not plugin_mode:
        try:
            mcp_config = _merged_mcp_config(mcp_path, force=args.force)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1

    if args.dry_run:
        print(f"已选择 Harness profile: {selected_profile}")
        if mcp_config is None:
            print("Marketplace 插件模式：不写入 .mcp.json，plugin.json 已提供 MCP。")
        else:
            print(f"将合并 {mcp_path.name}:")
            print(json.dumps(mcp_config, indent=2), end="\n")
        print(f"将写入 {harness_path.name}:")
        print(harness_text, end="")
        return 0

    if mcp_config is not None:
        _write_json_atomically(mcp_path, mcp_config)
    harness_path.write_text(harness_text, encoding="utf-8")
    StopGateStateStore().trust_config(target, harness_path)
    write_phase(target, "init", one_shot=True)

    # 验证 MCP 服务是否可用
    print("\n✅ 已创建配置文件:")
    if mcp_config is not None:
        print(f"   - {mcp_path.name}（已保留其他 MCP server）")
    else:
        print("   - Marketplace MCP（来自 plugin.json）")
    print(f"   - {harness_path.name}")
    print(f"   - Profile: {selected_profile}")

    # 测试 MCP 服务
    print("\n🔍 验证 MCP 服务...")
    try:
        available, detail = _verify_mcp_runtime()
        if available:
            print("✅ MCP 服务运行时可用")
        else:
            print(f"⚠️  MCP 服务运行时不可用: {detail}")
    except Exception as e:
        print(f"⚠️  无法验证 MCP 服务: {e}")

    print("\n📝 下一步:")
    print("   1. 重启 Claude Code 以加载 MCP 配置")
    print("   2. 运行 'entrix --help' 验证命令可用性")
    print("   3. 运行 'entrix harness validate' 验证配置")

    return 0


def cmd_phase(args: argparse.Namespace) -> int:
    """为仓库设置短期有效的 Stop Gate 阶段。"""
    target = Path(args.repo).resolve() if args.repo else Path.cwd().resolve()
    if args.mode == "clear":
        removed = clear_phase(target, session_id=getattr(args, "session_id", None))
        print(f"已清理 {target} 的 Stop Gate 阶段标记（{removed} 个）")
        return 0
    write_phase(target, args.mode, session_id=getattr(args, "session_id", None))
    print(f"已将 {target} 的 Stop Gate 阶段设置为 {args.mode}")
    return 0


def cmd_trust(args: argparse.Namespace) -> int:
    """Explicitly approve the current Harness config for Stop Hook execution."""
    target = Path(args.repo).resolve() if args.repo else Path.cwd().resolve()
    config_path = _find_harness_config(target)
    if config_path is None:
        print("未找到 harness.yaml 或 .harness/harness.yaml", file=sys.stderr)
        return 1
    StopGateStateStore().trust_config(target, config_path)
    print(f"已信任 Harness 配置：{config_path}")
    return 0


def cmd_harness_validate(args: argparse.Namespace) -> int:
    """验证harness.yaml配置。"""
    config_path = Path(args.config).resolve() if args.config else Path.cwd() / "harness.yaml"

    try:
        config = load_harness_config(config_path)
        print(f"有效的 harness 配置: {config_path}")
        print(f"  版本: {config.version}")
        print(f"  证据生产者: {len(config.evidence_producers)}")
        print(f"  门禁策略: {len(config.gate_policies)}")
        return 0
    except Exception as e:
        print(f"无效的配置: {e}", file=sys.stderr)
        return 1


def cmd_harness_run(args: argparse.Namespace) -> int:
    """执行harness收集和门禁裁决。"""
    repo_root = Path.cwd()
    config_path: Path | None
    if args.config:
        config_path = Path(args.config).resolve()
    else:
        config_path = _find_harness_config(repo_root)
        if config_path is None:
            print("未找到 harness.yaml 或 .harness/harness.yaml", file=sys.stderr)
            return 1

    try:
        runner = HarnessRunner(
            config_path,
            evidence_root=repo_root,
            parallel_producers=args.parallel,
            max_parallel_producers=args.max_workers if args.parallel else None,
        )
        result = runner.run(
            {
                "workspace": repo_root,
                "task_id": "manual-run",
                "changed_files": [],
                "branch": "manual",
                "base_ref": "HEAD",
            }
        )
        verdict = result.verdict
        bundle = result.bundle

        # 输出结果
        if args.json:
            output = {
                "status": verdict.status.value,
                "summary": verdict.summary,
                "evidence_count": len(bundle.evidence) if bundle else 0,
                "gate_results": [
                    {
                        "policy": gate_result.policy_name,
                        "severity": gate_result.severity.value,
                        "passed": gate_result.passed,
                        "active": gate_result.active,
                        "message": gate_result.message,
                    }
                    for gate_result in verdict.gate_results
                ],
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(f"\n{'=' * 50}")
            print(f"Verdict: {verdict.status.value.upper()}")
            print(f"{'=' * 50}")
            print(f"Summary: {verdict.summary}")
            if bundle is not None:
                print(f"已收集 {len(bundle.evidence)} 条证据", file=sys.stderr)

            if verdict.gate_results:
                print("\nGate results:")
                for gate_result in verdict.gate_results:
                    status_icon = "✓" if gate_result.passed else "✗"
                    print(
                        f"  {status_icon} {gate_result.policy_name} "
                        f"({gate_result.severity.value}): {gate_result.message}"
                    )

        # 返回适当的退出码
        return 0 if verdict.status.value == "pass" else 1

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


def cmd_serve(args: argparse.Namespace) -> int:
    """运行 Entrix MCP server。"""
    from entrix.server import create_server

    create_server().run(transport="stdio")
    return 0


def cmd_stop_gate(args: argparse.Namespace) -> int:
    """作为 Claude Code Stop hook 运行质量门禁。"""
    if getattr(args, "action", None) == "retry":
        return cmd_stop_gate_retry(args)
    from entrix.stop_gate.hook import main as stop_gate_hook_main

    hook_args: list[str] = []
    if args.timeout is not None:
        hook_args += ["--timeout", str(args.timeout)]
    if args.base:
        hook_args += ["--base", args.base]
    return stop_gate_hook_main(hook_args)


def _resolve_cli_repo(args: argparse.Namespace) -> Path:
    return Path(args.repo).resolve() if getattr(args, "repo", None) else _find_project_root()


def _harness_status(project_root: Path, state_store: StopGateStateStore) -> dict[str, object]:
    config_path = _find_harness_config(project_root)
    if config_path is None:
        return {"path": None, "present": False, "trusted": False}
    return {
        "path": str(config_path),
        "present": True,
        "trusted": state_store.is_config_trusted(project_root, config_path),
    }


def _status_payload(project_root: Path, session_id: str) -> dict[str, Any]:
    state_store = StopGateStateStore()
    harness = _harness_status(project_root, state_store)
    session_phase = read_phase(project_root, session_id=session_id)
    workspace_phase = read_phase(project_root)
    cached = state_store.load(project_root, session_id)
    sessions_dir = state_store.sessions_dir(project_root)
    cached_count = len(tuple(sessions_dir.glob("*.json"))) if sessions_dir.is_dir() else 0
    return {
        "version": PACKAGE_VERSION,
        "workspace": str(project_root),
        "branch": _current_branch(project_root),
        "session_id": session_id,
        "harness": harness,
        "phase": {
            "session": session_phase,
            "workspace": workspace_phase,
            "effective": session_phase or workspace_phase,
        },
        "stop_gate": {
            "cached_verdict": None
            if cached is None
            else {
                "fingerprint": cached.fingerprint,
                "status": cached.status,
                "summary": cached.summary,
            },
            "cached_session_count": cached_count,
        },
        "state": {
            "directory": str(state_store.state_dir),
            "exists": state_store.state_dir.exists(),
        },
    }


def _current_branch(project_root: Path) -> str:
    from entrix.gitinfo import current_branch

    return current_branch(project_root, timeout=5.0)


def cmd_status(args: argparse.Namespace) -> int:
    """显示当前 Harness、阶段和 Stop Gate 缓存状态。"""
    project_root = _resolve_cli_repo(args)
    session_id = getattr(args, "session_id", None) or "unknown-session"
    payload = _status_payload(project_root, session_id)
    if args.json:
        _print_json(payload)
        return 0

    harness = payload["harness"]
    phase = payload["phase"]
    stop_gate = payload["stop_gate"]
    state = payload["state"]
    print(f"Entrix {payload['version']} 状态")
    print(f"- 工作区: {payload['workspace']}")
    print(f"- 分支: {payload['branch']}")
    print(f"- Harness: {harness['path'] or '未配置'}")
    if harness["present"]:
        print(f"- Trust: {'已信任' if harness['trusted'] else '未信任'}")
    print(f"- Phase: {phase['effective'] or '未设置'}")
    verdict = stop_gate["cached_verdict"]
    print(f"- Stop Gate 缓存: {verdict['status'] if verdict else '无'}")
    print(f"- 状态目录: {state['directory']} ({'存在' if state['exists'] else '尚未创建'})")
    return 0


def _doctor_check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def cmd_doctor(args: argparse.Namespace) -> int:
    """检查插件运行时、Harness 信任和本地状态目录。"""
    project_root = _resolve_cli_repo(args)
    state_store = StopGateStateStore()
    checks: list[dict[str, str]] = [
        _doctor_check("version", "pass", f"Entrix {PACKAGE_VERSION}"),
        _doctor_check("python", "pass", f"{platform.python_version()} ({sys.executable})"),
    ]

    config_path = _find_harness_config(project_root)
    if config_path is None:
        checks.append(_doctor_check("harness", "warn", "未找到 harness.yaml；Stop Gate 对此工作区不生效"))
    else:
        try:
            load_harness_config(config_path)
        except Exception as error:  # noqa: BLE001
            checks.append(_doctor_check("harness", "error", f"配置无效: {error}"))
        else:
            checks.append(_doctor_check("harness", "pass", str(config_path)))
            if state_store.is_config_trusted(project_root, config_path):
                checks.append(_doctor_check("trust", "pass", "当前 Harness 配置已信任"))
            else:
                checks.append(_doctor_check("trust", "error", "配置未信任；运行 entrix trust --repo <path>"))

    state_dir = state_store.state_dir
    state_parent = state_dir.parent
    if state_dir.exists():
        writable = os.access(state_dir, os.W_OK)
    else:
        writable = state_parent.exists() and os.access(state_parent, os.W_OK)
    checks.append(
        _doctor_check(
            "state",
            "pass" if writable else "error",
            f"{state_dir} {'可写' if writable else '不可写'}",
        )
    )

    node_path = shutil.which("node") or shutil.which("node.exe")
    node_status = "pass" if node_path else ("error" if os.environ.get("CLAUDE_PLUGIN_ROOT") else "warn")
    checks.append(_doctor_check("node", node_status, node_path or "未找到 Node.js；Marketplace 插件启动器需要它"))

    openssl_path = shutil.which("openssl") or shutil.which("openssl.exe")
    checks.append(_doctor_check("openssl", "pass" if openssl_path else "warn", openssl_path or "未找到 OpenSSL；仅影响签名构建/备用校验"))

    try:
        mcp_available, mcp_detail = _verify_mcp_runtime()
    except Exception as error:  # noqa: BLE001
        mcp_available, mcp_detail = False, str(error)
    checks.append(_doctor_check("mcp", "pass" if mcp_available else "warn", mcp_detail or "FastMCP runtime 可用"))

    payload = {"version": PACKAGE_VERSION, "workspace": str(project_root), "checks": checks}
    if args.json:
        _print_json(payload)
    else:
        print(f"Entrix doctor: {project_root}")
        for check in checks:
            print(f"- [{check['status'].upper()}] {check['name']}: {check['detail']}")
    return 1 if any(check["status"] == "error" for check in checks) else 0


def cmd_stop_gate_retry(args: argparse.Namespace) -> int:
    """删除一个 session 的 Stop Gate 缓存，让下一次调用重新运行。"""
    target = _resolve_cli_repo(args)
    state_store = StopGateStateStore()
    session_id = getattr(args, "session_id", None) or "unknown-session"
    cached = state_store.load(target, session_id)
    state_store.delete(target, session_id)
    if cached is None:
        print(f"未找到 session {session_id} 的 Stop Gate 缓存；下一次调用仍会重新检查。")
    else:
        print(f"已清理 session {session_id} 的 Stop Gate 缓存（原状态: {cached.status}）。")
    return 0


def _find_harness_config(project_root: Path) -> Path | None:
    """查找项目根目录的 Harness 配置。"""
    from entrix.harness.config import find_harness_config as _find_config

    return _find_config(project_root)


def _load_project_harness(
    project_root: Path,
    config_path: Path | None = None,
) -> HarnessConfig:
    """加载项目 Harness 配置，供显式质量命令共享。"""
    selected_path = config_path or _find_harness_config(project_root)
    if selected_path is None:
        raise FileNotFoundError(f"未找到 Harness 配置：{project_root / 'harness.yaml'}")
    return load_harness_config(selected_path)


def _print_json(data: dict) -> None:
    from entrix.cli_runtime import print_json

    print_json(data)


def _print_review_trigger_report(report: dict) -> None:
    print("REVIEW TRIGGER REPORT")
    print(f"Base: {report['base']}")
    stats = report.get("diff_stats", {})
    print(
        "Diff stats: "
        f"files={stats.get('file_count', 0)} "
        f"added={stats.get('added_lines', 0)} "
        f"deleted={stats.get('deleted_lines', 0)}"
    )
    if report.get("human_review_required"):
        print("Human review required: yes")
        for trigger in report.get("triggers", []):
            print(f"- {trigger['name']} [{trigger['severity']}]")
            for reason in trigger.get("reasons", []):
                print(f"  reason: {reason}")
    else:
        print("Human review required: no")


def _domains_from_files(files: list[str]) -> set[str]:
    return get_project_preset().domains_from_files(files)


def _metric_domains(metric: Metric) -> set[str]:
    return get_project_preset().metric_domains(metric)


def _collect_run_files(args: argparse.Namespace, project_root: Path) -> list[str]:
    explicit_files = args.files or []
    if explicit_files:
        return explicit_files
    if args.changed_only:
        return collect_changed_files(project_root, args.base)
    return []


def cmd_run(args: argparse.Namespace) -> int:
    """将架构 fitness 函数作为可执行的 guardrail 检查运行。"""
    project_root = (
        Path(args.repo).resolve()
        if getattr(args, "repo", None)
        else _find_project_root()
    )
    try:
        harness_config = _load_project_harness(project_root)
    except (FileNotFoundError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    preset = get_project_preset()
    run_started_at = time.perf_counter()

    tier_filter = Tier(args.tier) if args.tier else None
    execution_scope = ExecutionScope(args.scope) if args.scope else ExecutionScope.LOCAL
    policy = GovernancePolicy(
        tier_filter=tier_filter,
        parallel=args.parallel,
        max_workers=getattr(args, "max_workers", 4),
        dry_run=args.dry_run,
        verbose=args.verbose,
        stream_output=args.stream,
        min_score=args.min_score,
        execution_scope=execution_scope,
        dimension_filters=tuple(args.dimension or ()),
        metric_filters=tuple(args.metric or ()),
    )

    output_format = getattr(args, "format", "text")
    reporter = TerminalReporter(verbose=policy.verbose)
    shell_output = _ShellOutputController(reporter, mode=policy.stream_output)
    live_reporter = (
        RichLiveProgressReporter(
            stream=sys.stdout,
            refresh_per_second=max(1, int(args.progress_refresh)),
        )
        if output_format == "rich" and sys.stdout.isatty() and not policy.dry_run
        else None
    )
    reporter.print_header(
        dry_run=policy.dry_run,
        tier=args.tier,
        parallel=policy.parallel,
    )

    changed_files = _collect_run_files(args, project_root)
    if args.changed_only or changed_files:
        if args.changed_only and not changed_files:
            print("No changed files detected; skipping fitness run.")
            write_report_output(
                args.output,
                {
                    "final_score": 0.0,
                    "hard_gate_blocked": False,
                    "score_blocked": False,
                    "dimensions": [],
                },
            )
            _cli_runtime.emit_runtime_fitness_event(
                project_root,
                status="skipped",
                tier=args.tier,
                report=None,
                metric_count=0,
                duration_ms=0.0,
                artifact_path=None,
                runtime_root_resolver=_runtime_root,
            )
            return 0

        changed_domains = preset.domains_from_files(changed_files)
        print(
            f"\nIncremental mode: base={args.base}, changed_files={len(changed_files)}, domains={','.join(sorted(changed_domains)) or 'none'}"
        )
    report, dimensions = run_fitness_report(
        project_root,
        policy,
        preset,
        dimensions=harness_config.fitness_dimensions,
        changed_files=changed_files or None,
        base=args.base,
        progress_setup_callback=(None if live_reporter is None else live_reporter.setup),
        progress_callback=(
            None
            if policy.dry_run
            else (
                live_reporter.handle_progress
                if live_reporter is not None
                else shell_output.handle_progress
            )
        ),
        shell_output_callback=(
            None
            if policy.dry_run or live_reporter is not None or output_format != "text" or not shell_output.should_capture_output
            else shell_output.handle_output
        ),
    )
    if live_reporter is not None:
        live_reporter.close()

    if not dimensions:
        print("No metrics matched the current run filters; skipping fitness run.")
        write_report_output(
            args.output,
            {
                "final_score": 0.0,
                "hard_gate_blocked": False,
                "score_blocked": False,
                "dimensions": [],
            },
        )
        _cli_runtime.emit_runtime_fitness_event(
            project_root,
            status="skipped",
            tier=args.tier,
            report=None,
            metric_count=0,
            duration_ms=0.0,
            artifact_path=None,
            runtime_root_resolver=_runtime_root,
        )
        return 0

    if output_format == "text":
        for dim, ds in zip(dimensions, report.dimensions, strict=True):
            print(f"\n## {dim.name.upper()} (weight: {dim.weight}%)")
            print(f"   Source: {dim.source_file}")

            for result in ds.results:
                state_labels: dict[ResultState | None, str] = {
                    ResultState.PASS: "\u2705 PASS",
                    ResultState.FAIL: "\u274c FAIL",
                    ResultState.UNKNOWN: "\u2753 UNKNOWN",
                    ResultState.SKIPPED: "\u23ed\ufe0f SKIPPED",
                    ResultState.WAIVED: "\u26a0\ufe0f WAIVED",
                }
                status = state_labels.get(result.state, "\u2753 UNKNOWN")
                hard = " [HARD GATE]" if result.hard_gate else ""
                tier_label = f" [{result.tier.value}]" if tier_filter else ""
                print(f"   - {result.metric_name}: {status}{hard}{tier_label}")

                if result.state == ResultState.FAIL and (policy.verbose or result.hard_gate):
                    if result.output:
                        lines = result.output.strip().split("\n")
                        for line in lines[:10]:
                            print(f"     > {line}")
                        if len(lines) > 10:
                            print(f"     > ... ({len(lines) - 10} more lines)")

            if ds.total > 0:
                print(f"   Score: {ds.score:.0f}%")

        reporter.print_footer(report)
    elif output_format == "ascii":
        AsciiReporter().report(report)
    else:
        RichReporter().report(report)

    write_report_output(args.output, report_to_dict(report))
    exit_code = enforce(report, policy)
    duration_ms = (time.perf_counter() - run_started_at) * 1000.0
    observed_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    artifact_path = str(
        _cli_runtime.fitness_artifact_path(
            project_root, tier=args.tier, observed_at_ms=observed_at_ms
        )
    )
    snapshot = _cli_runtime.build_runtime_fitness_snapshot(
        project_root,
        tier=args.tier,
        report=report,
        duration_ms=duration_ms,
        artifact_path=artifact_path,
        observed_at_ms=observed_at_ms,
        producer="entrix",
        base_ref=(args.base if changed_files else None),
        changed_files=changed_files,
    )
    artifact_path = _cli_runtime.write_runtime_fitness_artifacts(
        project_root,
        tier=args.tier,
        snapshot=snapshot,
        observed_at_ms=observed_at_ms,
        runtime_root_resolver=_runtime_root,
    )
    _cli_runtime.emit_runtime_fitness_event(
        project_root,
        status="passed" if exit_code == 0 else "failed",
        tier=args.tier,
        report=report,
        metric_count=sum(len(ds.results) for ds in report.dimensions),
        duration_ms=duration_ms,
        artifact_path=artifact_path,
        runtime_root_resolver=_runtime_root,
    )
    return exit_code


def cmd_validate(args: argparse.Namespace) -> int:
    """验证 dimension 权重之和为 100%。"""
    project_root = _find_project_root()
    try:
        config = _load_project_harness(project_root)
    except (FileNotFoundError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    dimensions = config.fitness_dimensions
    valid, total = validate_weights(dimensions)

    for dim in dimensions:
        print(f"  {dim.name}: {dim.weight}%  ({dim.source_file})")

    print(f"\nTotal: {total}%")
    if valid:
        print("\u2705 Weights sum to 100%")
        return 0

    print(f"\u274c Weights sum to {total}%, expected 100%")
    return 1


def cmd_review_trigger(args: argparse.Namespace) -> int:
    """针对当前 diff 评估 review-trigger 规则。"""
    project_root = _find_project_root()
    try:
        config = _load_project_harness(
            project_root,
            Path(args.config).resolve() if args.config else None,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    rules = config.review_trigger_rules
    changed_files = args.files or collect_review_changed_files(project_root, args.base)
    diff_stats = collect_diff_stats(project_root, args.base)
    report = evaluate_review_triggers(
        rules,
        changed_files,
        diff_stats,
        base=args.base,
        repo_root=project_root,
    )

    if args.json:
        _print_json(report.to_dict())
    else:
        _print_review_trigger_report(report.to_dict())

    if report.human_review_required and args.fail_on_trigger:
        return 3
    return 0


def _set_command_group_help(
    parser: HintingArgumentParser, command_path: tuple[str, ...]
) -> None:
    parser.command_path = ("entrix", *command_path)
    parser.set_defaults(_help_parser=parser)


def _command_path(args: argparse.Namespace) -> tuple[str, ...]:
    command = getattr(args, "command", None)
    if not command:
        return ()
    nested_commands = {
        "harness": "harness_command",
        "hook": "hook_command",
        "analyze": "analyze_command",
        "graph": "graph_command",
    }
    nested = getattr(args, nested_commands.get(command, ""), None)
    return (command, nested) if nested else (command,)


def build_parser() -> HintingArgumentParser:
    parser = HintingArgumentParser(
        prog="entrix",
        description="Entrix 可执行质量门禁",
        epilog=(
            "常用命令：\n"
            "  entrix init                 初始化 .mcp.json 与 harness.yaml\n"
            "  entrix phase planning      标记当前回合为规划阶段\n"
            "  entrix status              查看当前配置、阶段和门禁缓存\n"
            "  entrix doctor              检查插件运行环境和信任状态\n"
            "  entrix trust               确认 Harness 配置允许自动执行\n"
            "  entrix harness validate     检查 Harness 配置\n"
            "  entrix run                  执行 Fitness 指标\n"
            "  entrix harness run --json   收集 evidence 并执行门禁裁决\n"
            "  entrix review-trigger       识别需要人工审查的改动\n"
            "  entrix stop-gate            作为 Claude Code Stop Hook 执行\n"
            "  entrix serve                启动 MCP 服务\n"
            "\n"
            "命令提示：/entrix [init] [phase planning|implementation] "
            "[harness validate|run] [run] [stop-gate] [--repo <path>]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {PACKAGE_VERSION}",
        help="显示 Entrix 版本",
    )
    _set_command_group_help(parser, ())
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run guardrail checks")
    run_parser.add_argument(
        "--repo",
        default=None,
        help="项目根目录（默认从当前目录向上探测）",
    )
    run_parser.add_argument(
        "--tier", choices=["fast", "normal", "deep"], help="Run only metrics up to this tier"
    )
    run_parser.add_argument("--parallel", action="store_true", help="Run metrics in parallel")
    run_parser.add_argument(
        "--max-workers",
        type=_positive_int,
        default=4,
        help="Maximum concurrently running metrics when --parallel is set",
    )
    run_parser.add_argument("--dry-run", action="store_true", help="Show what would run")
    run_parser.add_argument("--verbose", action="store_true", help="Show output on failure")
    run_parser.add_argument(
        "--stream",
        nargs="?",
        choices=["off", "failures", "all"],
        const="all",
        default="failures",
        help="Stream shell metric stdout/stderr. Default: 'failures' (replay on fail). Use 'all' for live output, 'off' to suppress.",
    )
    run_parser.add_argument(
        "--format",
        choices=["text", "ascii", "rich"],
        default="text",
        help="Render final report as plain text, ASCII scorecard, or rich scorecard",
    )
    run_parser.add_argument(
        "--progress-refresh",
        type=int,
        default=4,
        help="Refresh rate for rich live progress updates",
    )
    run_parser.add_argument(
        "--min-score",
        type=float,
        default=80.0,
        help="Minimum weighted score before the run exits non-zero",
    )
    run_parser.add_argument(
        "--scope",
        choices=["local", "ci", "staging", "prod_observation"],
        help="Run only metrics for the given execution scope",
    )
    run_parser.add_argument(
        "--output",
        help="Write JSON report to a file path, or '-' for stdout",
    )
    run_parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Run only metrics relevant to changed files",
    )
    run_parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Explicit changed files used for incremental metric selection",
    )
    run_parser.add_argument(
        "--base",
        default="HEAD",
        help="Git base reference used by --changed-only",
    )
    run_parser.add_argument(
        "--dimension",
        action="append",
        default=[],
        help="Restrict execution to a dimension name; repeat to include multiple dimensions",
    )
    run_parser.add_argument(
        "--metric",
        action="append",
        default=[],
        help="Restrict execution to a metric name; repeat to include multiple metrics",
    )
    run_parser.set_defaults(func=cmd_run)

    install_parser = subparsers.add_parser(
        "install",
        help="Generate `.mcp.json` for Claude Code MCP integration",
    )
    install_parser.add_argument(
        "--repo",
        default=None,
        help="Optional repo root (defaults to current working directory).",
    )
    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print `.mcp.json` content without writing it.",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="明确替换已有的 entrix MCP 配置；其他 MCP server 始终保留。",
    )
    install_parser.set_defaults(func=cmd_install)

    init_parser = subparsers.add_parser("init", help="初始化 Harness（独立模式可合并 .mcp.json）")
    init_parser.add_argument(
        "--repo",
        default=None,
        help="Optional repo root (defaults to current working directory).",
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览 .mcp.json 与 harness.yaml，不写入文件。",
    )
    init_parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="auto",
        help="Harness 模板 profile；默认 auto，检测冲突时请显式选择。",
    )
    init_parser.add_argument("--force", action="store_true", help="覆盖已有 harness.yaml 并重建默认配置。")
    init_parser.set_defaults(func=cmd_init)

    phase_parser = subparsers.add_parser(
        "phase",
        help="设置当前 Stop Gate 阶段而不运行检查",
    )
    phase_parser.add_argument(
        "mode",
        choices=["planning", "implementation", "clear"],
        help="当前任务阶段",
    )
    phase_parser.add_argument(
        "--repo",
        default=None,
        help="Optional repo root (defaults to current working directory).",
    )
    phase_parser.add_argument(
        "--session-id",
        default=None,
        help="可选 Claude session id；提供后 phase 状态只对该 session 生效。",
    )
    phase_parser.set_defaults(func=cmd_phase)

    status_parser = subparsers.add_parser(
        "status",
        help="查看当前工作区、Harness、Phase 和 Stop Gate 缓存状态",
    )
    status_parser.add_argument("--repo", default=None, help="仓库根目录（默认自动探测）")
    status_parser.add_argument(
        "--session-id",
        default=None,
        help="Claude session id；默认使用 unknown-session",
    )
    status_parser.add_argument("--json", action="store_true", help="输出 JSON")
    status_parser.set_defaults(func=cmd_status)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="检查版本、Harness、信任、MCP 和插件运行时",
    )
    doctor_parser.add_argument("--repo", default=None, help="仓库根目录（默认自动探测）")
    doctor_parser.add_argument("--json", action="store_true", help="输出 JSON")
    doctor_parser.set_defaults(func=cmd_doctor)

    trust_parser = subparsers.add_parser(
        "trust",
        help="确认当前 Harness 配置允许 Stop Hook 自动执行其中的命令",
    )
    trust_parser.add_argument(
        "--repo",
        default=None,
        help="仓库根目录（默认当前目录）",
    )
    trust_parser.set_defaults(func=cmd_trust)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run Entrix MCP server over stdio.",
    )
    serve_parser.set_defaults(func=cmd_serve)

    stop_gate_parser = subparsers.add_parser(
        "stop-gate",
        help="Run the quality gate as a Claude Code Stop hook (reads hook payload from stdin)",
    )
    stop_gate_parser.add_argument(
        "action",
        nargs="?",
        choices=["retry"],
        help="retry 清理当前 session 的缓存裁决后重新运行",
    )
    stop_gate_parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Evidence collection timeout in seconds (env: ENTRIX_STOP_GATE_TIMEOUT).",
    )
    stop_gate_parser.add_argument(
        "--base",
        default=None,
        help="Optional git base ref for diff-based checks.",
    )
    stop_gate_parser.add_argument("--repo", default=None, help="retry 使用的仓库根目录")
    stop_gate_parser.add_argument("--session-id", default=None, help="retry 要清理的 Claude session id")
    stop_gate_parser.set_defaults(func=cmd_stop_gate)

    validate_parser = subparsers.add_parser("validate", help="Check dimension weights sum to 100%%")
    validate_parser.set_defaults(func=cmd_validate)

    review_trigger_parser = subparsers.add_parser(
        "review-trigger",
        help="Detect risky changes that should trigger human review",
    )
    review_trigger_parser.add_argument("files", nargs="*", help="Optional explicit changed files")
    review_trigger_parser.add_argument("--base", default="HEAD~1", help="Git diff base")
    review_trigger_parser.add_argument("--config", help="Optional review-trigger YAML config path")
    review_trigger_parser.add_argument(
        "--fail-on-trigger",
        action="store_true",
        help="Return non-zero when human review is required",
    )
    review_trigger_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    review_trigger_parser.set_defaults(func=cmd_review_trigger)

    release_trigger_parser = subparsers.add_parser(
        "release-trigger",
        help="Detect risky release-surface drift before publish",
    )
    release_trigger_parser.add_argument("files", nargs="*", help="Optional explicit changed files")
    release_trigger_parser.add_argument("--manifest", required=True, help="Release manifest JSON path")
    release_trigger_parser.add_argument("--baseline-manifest", help="Optional baseline manifest JSON path")
    release_trigger_parser.add_argument("--base", default="HEAD~1", help="Git diff base")
    release_trigger_parser.add_argument("--config", help="Optional release-trigger YAML config path")
    release_trigger_parser.add_argument(
        "--fail-on-trigger",
        action="store_true",
        help="Return non-zero when release review or block is required",
    )
    release_trigger_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    release_trigger_parser.set_defaults(func=cmd_release_trigger)

    # Harness system commands
    harness_parser = subparsers.add_parser("harness", help="Harness evidence collection and gate arbitration")
    _set_command_group_help(harness_parser, ("harness",))
    harness_subparsers = harness_parser.add_subparsers(dest="harness_command")

    harness_validate = harness_subparsers.add_parser("validate", help="Validate harness.yaml configuration")
    harness_validate.add_argument("config", nargs="?", default="harness.yaml", help="Path to harness.yaml (default: harness.yaml)")
    harness_validate.set_defaults(func=cmd_harness_validate)

    harness_run = harness_subparsers.add_parser("run", help="Execute harness collection and arbitration")
    harness_run.add_argument("--config", default="harness.yaml", help="Path to harness.yaml (default: harness.yaml)")
    harness_run.add_argument("--json", action="store_true", help="Emit JSON output")
    harness_run.add_argument(
        "--parallel",
        action="store_true",
        help="Run evidence producers in parallel within the harness.yaml limit",
    )
    harness_run.add_argument(
        "--max-workers",
        type=_positive_int,
        default=None,
        help="Requested producer workers when --parallel is set",
    )
    harness_run.set_defaults(func=cmd_harness_run)

    hook_parser = subparsers.add_parser("hook", help="Reusable local hook helpers")
    _set_command_group_help(hook_parser, ("hook",))
    hook_subparsers = hook_parser.add_subparsers(dest="hook_command")

    hook_file_length = hook_subparsers.add_parser(
        "file-length",
        help="Fail when staged or explicit source files exceed the configured line budget",
    )
    hook_file_length.add_argument(
        "--config",
        required=True,
        help="Path to a JSON file with file size budget configuration.",
    )
    hook_file_length.add_argument(
        "--staged-only",
        action="store_true",
        help="Evaluate only staged files from the git index.",
    )
    hook_file_length.add_argument(
        "--strict-limit",
        action="store_true",
        help="Ignore HEAD ratcheting and enforce configured limits directly.",
    )
    hook_file_length.add_argument(
        "--base",
        default="HEAD",
        help="Compatibility flag for changed-only style integrations.",
    )
    hook_file_length.add_argument("files", nargs="*", help="Optional explicit relative paths to evaluate")
    hook_file_length.set_defaults(func=cmd_hook_file_length)

    analyze_parser = subparsers.add_parser("analyze", help="Structured source analysis helpers")
    _set_command_group_help(analyze_parser, ("analyze",))
    analyze_subparsers = analyze_parser.add_subparsers(dest="analyze_command")

    analyze_long_file = analyze_subparsers.add_parser(
        "long-file",
        help="Return ClassMap/FunctionMap payloads for oversized or explicit files",
    )
    analyze_long_file.add_argument(
        "paths",
        nargs="*",
        help="Explicit files to analyze",
    )
    analyze_long_file.add_argument("--files", nargs="*", default=[], help="Explicit files to analyze")
    analyze_long_file.add_argument("--base", default="HEAD", help="Git base reference for implicit oversized-file discovery")
    analyze_long_file.add_argument(
        "--config",
        help="Path to a JSON file with file size budget configuration.",
    )
    analyze_long_file.add_argument(
        "--strict-limit",
        action="store_true",
        help="Ignore HEAD ratcheting and enforce configured limits directly.",
    )
    analyze_long_file.add_argument(
        "--min-lines",
        type=int,
        default=60,
        help="Hide text-report items smaller than this many lines (JSON output is unaffected).",
    )
    analyze_long_file.add_argument(
        "--comment-review-commit-threshold",
        type=int,
        default=5,
        help="Warn when a class/function has comments and changed in at least this many commits.",
    )
    analyze_long_file.add_argument("--json", action="store_true", help="Emit JSON output")
    analyze_long_file.set_defaults(func=cmd_analyze_long_file)

    graph_parser = subparsers.add_parser("graph", help="Graph-backed impact and test-radius analysis")
    _set_command_group_help(graph_parser, ("graph",))
    graph_subparsers = graph_parser.add_subparsers(dest="graph_command")

    graph_build = graph_subparsers.add_parser("build", help="Build or update the code graph")
    graph_build.add_argument("--base", default="HEAD", help="Git diff base for incremental update")
    graph_build.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_build.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_build.set_defaults(func=cmd_graph_build)

    graph_stats = graph_subparsers.add_parser("stats", help="Show graph statistics")
    graph_stats.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_stats.set_defaults(func=cmd_graph_stats)

    graph_impact = graph_subparsers.add_parser("impact", help="Analyze blast radius")
    graph_impact.add_argument("files", nargs="*", help="Optional explicit changed files")
    graph_impact.add_argument("--base", default="HEAD", help="Git diff base")
    graph_impact.add_argument("--depth", type=int, default=2, help="Traversal depth")
    graph_impact.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_impact.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_impact.set_defaults(func=cmd_graph_impact)

    graph_test_radius = graph_subparsers.add_parser(
        "test-radius",
        help="Estimate tests affected by changed files or commits",
    )
    graph_test_radius.add_argument("files", nargs="*", help="Optional explicit changed files")
    graph_test_radius.add_argument("--base", default="HEAD", help="Git diff base")
    graph_test_radius.add_argument("--depth", type=int, default=2, help="Traversal depth")
    graph_test_radius.add_argument("--max-targets", type=int, default=25, help="Max nodes to query")
    graph_test_radius.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_test_radius.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_test_radius.set_defaults(func=cmd_graph_test_radius)

    graph_test_mapping = graph_subparsers.add_parser(
        "test-mapping",
        help="Map changed source files to related tests with heuristic and graph evidence",
    )
    graph_test_mapping.add_argument("files", nargs="*", help="Optional explicit changed files")
    graph_test_mapping.add_argument("--base", default="HEAD", help="Git diff base")
    graph_test_mapping.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode for optional semantic enrichment",
    )
    graph_test_mapping.add_argument(
        "--no-graph",
        action="store_true",
        help="Disable graph enrichment and use heuristic mapping only",
    )
    graph_test_mapping.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Return non-zero when at least one source file has no asserted test mapping",
    )
    graph_test_mapping.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_test_mapping.set_defaults(func=cmd_graph_test_mapping)

    graph_query = graph_subparsers.add_parser("query", help="Run a graph query")
    graph_query.add_argument(
        "pattern",
        choices=[
            "callers_of",
            "callees_of",
            "imports_of",
            "importers_of",
            "children_of",
            "tests_for",
            "inheritors_of",
            "file_summary",
        ],
        help="Query pattern",
    )
    graph_query.add_argument("target", help="Qualified name or file path")
    graph_query.add_argument("--base", default="HEAD", help="Git diff base")
    graph_query.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_query.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_query.set_defaults(func=cmd_graph_query)

    graph_history = graph_subparsers.add_parser(
        "history",
        help="Estimate test radius for recent commits using the current graph",
    )
    graph_history.add_argument("--count", type=int, default=10, help="Number of commits to inspect")
    graph_history.add_argument("--ref", default="HEAD", help="Revision to walk from")
    graph_history.add_argument("--depth", type=int, default=2, help="Traversal depth")
    graph_history.add_argument("--max-targets", type=int, default=25, help="Max nodes to query")
    graph_history.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_history.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_history.set_defaults(func=cmd_graph_history)

    graph_review_context = graph_subparsers.add_parser(
        "review-context",
        help="Build an AI-friendly review context from the current graph",
    )
    graph_review_context.add_argument("files_positional", nargs="*", help="Optional explicit changed files")
    graph_review_context.add_argument("--files", nargs="*", default=[], help="Explicit changed files")
    graph_review_context.add_argument("--base", default="HEAD", help="Git diff base")
    graph_review_context.add_argument("--head", default="HEAD", help="Compatibility flag; currently unused")
    graph_review_context.add_argument("--depth", type=int, default=2, help="Traversal depth")
    graph_review_context.add_argument("--max-targets", type=int, default=25, help="Max nodes to query")
    graph_review_context.add_argument("--max-files", type=int, default=12, help="Max source files to include")
    graph_review_context.add_argument(
        "--max-lines-per-file",
        type=int,
        default=120,
        help="Max source lines to include per file",
    )
    graph_review_context.add_argument(
        "--no-source",
        action="store_true",
        help="Do not include source snippets in the output",
    )
    graph_review_context.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_review_context.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_review_context.add_argument("--output", help="Write JSON output to a file path or '-' for stdout")
    graph_review_context.set_defaults(func=cmd_graph_review_context)

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """Run Entrix CLI with consistent help and post-success guidance."""
    _configure_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        # 检查是否是子命令组，如果是则显示该组的子命令帮助
        if argv and len(argv) == 1 and argv[0] in ["harness", "graph", "hook", "analyze"]:
            show_subgroup_help(argv[0])
        else:
            print_command_overview()
        return 0

    args.command_path = _command_path(args)
    exit_code = args.func(args)
    if should_show_next_steps(args, exit_code):
        print_next_steps(args.command_path, sys.stderr)
    return exit_code


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
