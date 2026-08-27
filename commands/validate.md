---
description: 只读校验 harness.yaml 配置正确性
argument-hint: "[--repo <path>] [harness.yaml]"
allowed-tools: Bash(node:*)
---

校验配置 Schema、权重求和与引用完整性，不执行任何检查命令。

```bash
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" harness validate $ARGUMENTS
```

约束（详见 skills/entrix/SKILL.md）：

- validate 是纯只读操作。
- init 之后不能未经询问直接调用本命令，需先获得用户的校验许可。
