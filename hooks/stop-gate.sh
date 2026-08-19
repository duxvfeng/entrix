#!/usr/bin/env bash
# Entrix Stop Gate —— Claude Code Stop hook 包装器。
#
# 查找 entrix 的优先级：
#   1. 当前插件携带的无 Python 启动器（发布模式）
#   2. PATH 上的 entrix（开发模式）
#   3. uvx 或源码 Python（开发 fallback）
# 全部不可用时按 fail-closed 输出阻断决策。
#
# 手动禁用：export ENTRIX_STOP_GATE_DISABLED=1

set -uo pipefail

# 安全阀：显式禁用时直接放行
if [ -n "${ENTRIX_STOP_GATE_DISABLED:-}" ]; then
  echo "ENTRIX_STOP_GATE_DISABLED is set; Harness Stop Gate is bypassed." >&2
  exit 0
fi

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
block_unavailable() {
  printf '%s\n' '{"decision":"block","reason":"Entrix Stop Gate 不可用，已按 fail-closed 阻断。"}'
  echo "entrix stop-gate: 无法下载、校验或启动插件二进制。" >&2
  exit 0
}

if [ -n "$PLUGIN_ROOT" ] && [ -f "$PLUGIN_ROOT/bin/entrix" ]; then
  plugin_os="$(uname -s 2>/dev/null || true)"
  case "$plugin_os" in
    MINGW*|MSYS*|CYGWIN*)
    if command -v powershell.exe >/dev/null 2>&1 && [ -f "$PLUGIN_ROOT/bin/entrix-bootstrap.ps1" ]; then
      powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PLUGIN_ROOT/bin/entrix-bootstrap.ps1" stop-gate "$@"
      plugin_rc=$?
    else
      block_unavailable
    fi
    ;;
  *)
    if [ -x "$PLUGIN_ROOT/bin/entrix" ]; then
      "$PLUGIN_ROOT/bin/entrix" stop-gate "$@"
      plugin_rc=$?
    else
      bash "$PLUGIN_ROOT/bin/entrix" stop-gate "$@"
      plugin_rc=$?
    fi
    ;;
  esac
  [ "$plugin_rc" -eq 0 ] || block_unavailable
  exit 0
fi

if command -v entrix >/dev/null 2>&1; then
  exec entrix stop-gate "$@"
fi

if command -v uvx >/dev/null 2>&1; then
  exec uvx --quiet entrix stop-gate "$@"
fi

if [ -n "$PLUGIN_ROOT" ] && [ -f "$PLUGIN_ROOT/entrix/__init__.py" ] && command -v python3 >/dev/null 2>&1; then
  if PYTHONPATH="$PLUGIN_ROOT" python3 -c "import entrix, yaml" >/dev/null 2>&1; then
    exec env PYTHONPATH="$PLUGIN_ROOT" python3 -m entrix stop-gate "$@"
  fi
fi

printf '%s\n' '{"decision":"block","reason":"Entrix Stop Gate 不可用，已按 fail-closed 阻断。"}'
echo "entrix stop-gate: 未找到可用的 entrix（entrix/uvx/python3）。" >&2
echo "安装方式：pip install entrix 或安装 uv 后使用 uvx entrix" >&2
exit 0
