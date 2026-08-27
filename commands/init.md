---
description: 为当前仓库初始化 Entrix 质量 Harness 配置
argument-hint: "[--repo <path>] [--profile <name>]"
allowed-tools: Bash(node:*)
---

创建或修复仓库根目录的单文件质量护栏配置。

```bash
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" init $ARGUMENTS
```

约束（详见 skills/entrix/SKILL.md）：

- init 只创建/更新 `harness.yaml`，不注册 MCP 或 Stop Hook。
- 检测到多个语言 profile 时停止，请用户显式选择后再继续。
- 完成后必须询问："Configuration is ready. Do you want to run configuration
  validation or local checks now?" 在用户明确同意前不要运行校验或检查。
