#!/usr/bin/env bash
# 模拟 Claude Code Stop hook 调用环境

echo "=== 模拟 Claude Code Stop Hook 调用 ==="
echo "工作目录: $(pwd)"
echo "PATH: $PATH" | head -c 200
echo ""
echo "=== Hook 执行结果 ==="

# 清除可能影响测试的环境变量
unset CLAUDE_PLUGIN_ROOT
unset ENTRIX_STOP_GATE_DISABLED

# 调用 hook（模拟 Stop 操作，但没有实际参数）
bash ./hooks/stop-gate.sh --base HEAD 2>&1 | head -5

echo ""
echo "=== 退出状态 ==="
echo "Exit code: $?"