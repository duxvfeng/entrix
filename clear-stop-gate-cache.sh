#!/usr/bin/env bash
# 清理 Entrix Stop Gate 缓存状态

echo "=== 清理 Entrix Stop Gate 缓存 ==="

# 主要缓存目录
CACHE_DIRS=(
  "$TEMP/harness-monitor/runtime/state"
  "$TEMP/harness-monitor/stop-gate"
  "$HOME/.cache/entrix/stop-gate"
)

for dir in "${CACHE_DIRS[@]}"; do
  if [ -d "$dir" ]; then
    echo "清理目录: $dir"
    find "$dir" -name "*.json" -type f -delete 2>/dev/null && echo "  ✅ 清理完成" || echo "  ⚠️  部分文件无法删除"
  else
    echo "目录不存在: $dir"
  fi
done

echo ""
echo "=== 缓存清理完成 ==="
echo "如果问题仍然存在，请重启 Claude Code"