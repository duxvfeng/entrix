---
description: 检查当前变更是否命中需要人工审查的触发器
argument-hint: "[--repo <path>] [--json]"
allowed-tools: Bash(node:*)
---

按 harness.yaml 中内联的 review_triggers 规则评估变更风险。

```bash
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" review-trigger $ARGUMENTS
```

约束（详见 skills/entrix/SKILL.md）：

- 触发规则与策略均内联于 harness.yaml，不存在独立 trigger 文件；
  不要读取旁路配置。
