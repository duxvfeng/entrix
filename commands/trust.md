---
description: 确认信任当前 Harness 配置以启用 Stop Gate 自动执行
argument-hint: "[--repo <path>]"
allowed-tools: Bash(node:*)
---

对已有 harness.yaml 执行信任确认。未确认的配置不会在 Stop Hook 中自动执行命令。

```bash
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" trust $ARGUMENTS
```

约束（详见 skills/entrix/SKILL.md）：

- 打开已有仓库或修改 Harness 后，先运行本命令再依赖 Stop Gate。
- trust 绑定当前配置内容哈希；配置再变更后需重新确认。
