"""生命周期与运维子命令：install / init / phase / trust / status / doctor / stop-gate。

从 cli.py 拆出；fitness 相关命令仍留在 cli.py。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from entrix import __version__ as PACKAGE_VERSION
from entrix.cli_runtime import print_json as _print_json
from entrix.gitinfo import current_branch, find_project_root
from entrix.harness.config import find_harness_config as _find_harness_config
from entrix.harness.config import load_harness_config
from entrix.harness.profiles import ProfileDetectionError, resolve_profile
from entrix.harness.template import render_default_harness
from entrix.stop_gate.phase import clear_phase, read_phase, write_phase
from entrix.stop_gate.revalidation import StopGateStateStore


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
    return Path(args.repo).resolve() if getattr(args, "repo", None) else find_project_root()


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
        "branch": current_branch(project_root, timeout=5.0),
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
