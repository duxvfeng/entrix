# 阶段感知 Stop Gate 设计

## 背景

当前插件把 Claude Code 的所有 `Stop` 事件都交给 Stop Gate。这样可以覆盖代码交付，
但也会让纯头脑风暴、配置初始化和普通问答触发完整 Harness。对于 Java 多模块项目，
这还可能在没有交付代码的回合中启动 Maven、Surefire 或 Gradle。

## 目标

- 头脑风暴和规划阶段结束时不启动 Stop Gate。
- `entrix init` 只初始化配置；本次回合结束时一次性跳过 Stop Gate。
- 实现阶段结束时继续执行完整 Stop Gate，保留 fail-closed 语义。
- 现有未使用阶段命令的项目保持兼容：工作区存在变更时仍执行 Stop Gate。
- 阶段豁免不写入 `harness.yaml`，不形成永久安全绕过。

## 行为矩阵

| 阶段状态 | 工作区变更 | Stop Gate 行为 |
| --- | --- | --- |
| `planning` | 任意 | 放行，不收集 Evidence |
| `init` 一次性标记 | 任意 | 放行并消费标记 |
| `implementation` | 任意 | 执行完整 Harness |
| 无标记 | 无变更 | 放行，视为普通规划/问答回合 |
| 无标记 | 有变更 | 执行完整 Harness，兼容直接编辑工作流 |

`ENTRIX_STOP_GATE_DISABLED` 仍是显式紧急旁路；阶段状态不是它的替代品。

## 架构

新增 `entrix.stop_gate.phase`，负责在工作区的 `.harness/runtime/phase.json` 中读写短期
阶段状态。该目录属于运行时状态，不参与 Harness 配置和 Git 版本控制。

状态至少包含：

```json
{
  "schema_version": "stop-gate-phase/v1",
  "workspace": "D:/repo",
  "mode": "planning",
  "one_shot": false,
  "created_at": "2026-08-18T10:00:00Z",
  "expires_at": "2026-08-18T18:00:00Z"
}
```

状态读取失败、路径不匹配或已过期时按“无标记”处理；实现阶段仍会因工作区变更触发
兼容路径，不将损坏的短期状态升级成全局阻断。

Stop Hook 的顺序调整为：

1. 检查紧急旁路和 Harness 配置。
2. 读取并处理阶段标记；`init` 标记立即消费，`planning` 直接放行。
3. 收集工作区变更；无标记且无变更时放行。
4. 只有 `implementation` 标记或存在变更时，进入现有指纹、缓存、Harness 收集和 Gate 仲裁流程。

新增 `entrix phase planning` 与 `entrix phase implementation`，供 Claude skill 在规划和
开始实现时设置阶段。`entrix init` 成功写入配置后自动写入一次性 `init` 标记。CLI 阶段
命令只写运行时状态，不运行任何检查。

## Claude skill 协议

打包 skill 在开始 `/entrix` 规划时设置 `planning`；用户批准并开始修改代码时设置
`implementation`。初始化流程不手工设置阶段，使用 `entrix init` 自动写入的一次性标记，
然后等待用户确认是否执行检查。

没有通过 skill 设置阶段的直接 CLI/编辑仍由“有变更则运行”兼容路径保护。

## 错误处理与安全边界

- 阶段文件只影响触发时机，不改变 Gate 的通过条件、Evidence 格式或 fail-closed 裁决。
- `planning` 和 `init` 只跳过本次 Stop Gate，不修改 Harness 配置。
- 阶段文件采用原子写入；状态过期或损坏时删除并回退到兼容路径。
- `init` 标记只能消费一次，避免用户拒绝检查后一直绕过门禁。
- 阶段状态按工作区而非 Claude 会话隔离；并发会话可能互相覆盖，skill 必须在开始实现
  前显式写入 `implementation`，避免遗留 `planning` 标记影响实现回合。
- 不增加 YAML 永久 `skip_stop_gate` 开关，也不根据文件名猜测 Maven、Gradle 或 Java。

## 验收标准

1. 纯规划且工作区无变更时，Stop Hook 不构造 Harness Runner。
2. `planning` 阶段即使存在变更也不构造 Harness Runner。
3. `implementation` 阶段即使没有 Git 变更也会构造并运行 Harness Runner。
4. `init` 标记只跳过一次，并在读取后删除。
5. 无阶段标记但存在变更时，现有 Stop Gate 行为保持不变。
6. `entrix init` 和 `entrix phase` 不执行验证、Fitness、Harness 或 Stop Gate。
7. 配置错误、Runner 错误和 Gate 失败仍输出原有 block 决策。
