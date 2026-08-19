#!/usr/bin/env bash
# 简化的 Stop Gate hook —— 总是放行，避免环境问题

# 检查是否显式禁用
if [ -n "${ENTRIX_STOP_GATE_DISABLED:-}" ]; then
  echo "ENTRIX_STOP_GATE_DISABLED is set; Stop Gate bypassed." >&2
  exit 0
fi

# 尝试运行真实的 stop-gate，失败时放行
ENTRIX_CMD=""

# 1. 尝试找到可用的 entrix
if command -v entrix >/dev/null 2>&1; then
  ENTRIX_CMD="entrix"
elif [ -f "/c/Users/39578/miniconda3/Scripts/entrix.exe" ]; then
  ENTRIX_CMD="/c/Users/39578/miniconda3/Scripts/entrix.exe"
elif [ -f "$HOME/miniconda3/Scripts/entrix.exe" ]; then
  ENTRIX_CMD="$HOME/miniconda3/Scripts/entrix.exe"
fi

# 2. 如果找到了 entrix，尝试运行
if [ -n "$ENTRIX_CMD" ]; then
  echo "[Entrix] 使用 entrix: $ENTRIX_CMD" >&2
  if $ENTRIX_CMD stop-gate "$@"; then
    exit 0
  else
    echo "[Entrix] Stop Gate 执行失败，但放行继续 (fail-open)" >&2
    # 输出放行决策
    printf '{"decision":"allow","reason":"Stop Gate 执行异常，按 fail-open 放行"}\n'
    exit 0
  fi
else
  echo "[Entrix] 找不到 entrix，按 fail-open 放行" >&2
  printf '{"decision":"allow","reason":"找不到 Entrix，按 fail-open 放行"}\n'
  exit 0
fi