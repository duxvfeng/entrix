---
description: 标记当前任务阶段为规划或实现
argument-hint: "<planning|implementation> [--repo <path>]"
allowed-tools: Bash(node:*)
---

切换 Stop Gate 的阶段标记，参数必需且只能是 planning 或 implementation。

```bash
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" phase $ARGUMENTS
```

约束（详见 skills/entrix/SKILL.md）：

- 若 $ARGUMENTS 首词不是 planning 或 implementation，先向用户澄清再执行。
- 规划或头脑风暴开始时设 planning；仅在用户明确批准实现后才设 implementation。
