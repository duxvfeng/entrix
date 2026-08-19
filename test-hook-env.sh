#!/usr/bin/env bash
# 模拟 Claude Code 调用 hook 的环境

echo "=== Hook 执行环境测试 ==="
echo "PATH: $PATH"
echo "SHELL: $SHELL"
echo "USER: $USER"
echo "HOME: $HOME"
echo " uname: $(uname -s) $(uname -m)"
echo ""

echo "=== entrix 命令检查 ==="
which entrix && echo "✅ 找到 entrix: $(which entrix)" || echo "❌ 找不到 entrix"
command -v entrix && echo "✅ command -v entrix: $(command -v entrix)" || echo "❌ command -v 找不到 entrix"
where entrix 2>/dev/null || echo "where command 未找到"
echo ""

echo "=== 测试 hook 脚本 ==="
bash hooks/stop-gate.sh --help 2>&1 | head -5
echo ""

echo "=== CLAUDE_PLUGIN_ROOT ==="
echo "CLAUDE_PLUGIN_ROOT: ${CLAUDE_PLUGIN_ROOT:-未设置}"
