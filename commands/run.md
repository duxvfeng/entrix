---
description: 执行 fast 层级本地质量检查
argument-hint: "[--repo <path>] [--json]"
allowed-tools: Bash(node:*)
---

对当前仓库执行 fast tier 检查并汇总结果。

```bash
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" run --tier fast $ARGUMENTS
```

约束（详见 skills/entrix/SKILL.md）：

- 本命令真实执行检查（非 dry-run）。
- Marketplace 安装下，完整 Harness 运行的唯一权威入口是 Stop Hook；
  不要把本命令作为停止前的重复检查调用。
