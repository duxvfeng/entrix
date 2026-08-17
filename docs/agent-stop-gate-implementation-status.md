# Claude Stop Gate 闭环实施状态（未完成）

> 状态：未完成设计文档
>
> 本文记录 Entrix 当前已经具备的质量门禁能力，以及尚未实现的
> `Claude Stop -> Harness 取证 -> Gate Arbiter 裁决 -> 失败回流 -> 再次验证`
> 自动闭环。本文不是功能已交付声明，也不应被用作通过验收的依据。

## 1. 目标

在 Claude 表示任务完成并尝试结束时，系统必须由独立的 Harness 收集
可复核证据并进行裁决。只有裁决为 `PASS` 时，Claude 才能结束本次任务；
裁决为 `FAIL` 时，系统必须把结构化失败原因反馈给 Claude，要求其继续修改。
Claude 下一次发出停止请求后，Harness 必须重新执行完整裁决，而不是复用旧结果。

目标闭环如下：

```text
Claude 编码
  -> Claude 请求 Stop
  -> Stop Gate 拦截请求
  -> Harness 独立收集证据
  -> Gate Arbiter 裁决
       -> PASS: 放行 Stop
       -> FAIL: 生成失败反馈并恢复 Claude 工作状态
  -> Claude 修改
  -> Claude 再次请求 Stop
  -> 重新收集证据并裁决
```

## 2. 当前实现基线

Entrix 已经实现的是可独立执行的质量检查器，而不是 Claude 生命周期控制器。

| 能力 | 当前状态 | 现有实现 |
| --- | --- | --- |
| 运行质量指标 | 已实现 | `entrix run` 运行 shell、SARIF、图谱探针等指标。 |
| 保存检查结果 | 已实现 | 生成 JSON 报告、运行 artifact、事件记录和 fitness mailbox 消息。 |
| 硬门禁判定 | 已实现 | 硬门禁失败返回退出码 `2`；分数不足返回退出码 `1`。 |
| 风险变更识别 | 已实现 | `review-trigger` 可要求人工审查，并可选返回非零退出码。 |
| Claude MCP 集成 | 部分实现 | ✅ 已有：`entrix serve` 提供 MCP 服务，Claude 可**主动查询** Entrix 结果<br>❌ 缺少：MCP **推送**事件给 Claude（如 FAIL 通知）<br>❌ 缺少：MCP **拦截** Claude Stop 请求 |
| Stop 事件拦截 | 未实现 | 没有 Claude `Stop` hook、停止事件协议或等价入口。 |
| Gate Arbiter | 未实现 | 没有消费证据并输出最终 `PASS`/`FAIL` 的独立组件。 |
| 阻止 Claude 结束 | 未实现 | Entrix 的退出码只影响命令调用方，不能控制 Claude 会话结束。 |
| FAIL 回流 Claude | 未实现 | 没有将失败项转换为可继续执行的 agent 反馈消息。 |
| 自动重试闭环 | 未实现 | 没有会话状态、尝试次数、重新取证或恢复工作状态的编排。 |

当前 `entrix run` 的流程是：执行指标、计算分数、写入报告，然后向调用进程
返回退出码。它不持有 Claude 会话标识，也不接收或处理 Stop 请求。

## 3. 已有组件及其边界

### 3.1 Entrix Fitness Runner

责任：根据 `harness.yaml` 中的规则执行客观质量指标，形成单次运行报告。

已有输出应作为 Gate Arbiter 的证据输入，包括：

- 每个 metric 的状态、输出、耗时和是否为硬门禁；
- 总分、硬门禁阻断状态、分数阻断状态；
- JSON 报告文件；
- runtime artifact；
- `events.jsonl` 中的运行事件；
- `mailbox/fitness/new` 中的消息。

不应由 Fitness Runner 负责的事项：

- 判断 Claude 是否允许结束；
- 解释用户需求是否已完成；
- 向 Claude 发送下一轮修改指令；
- 管理 Stop 尝试次数。

### 3.2 Review Trigger

责任：根据变更路径、变更规模和边界变化识别需要更高等级审查的变更。

它当前是独立命令。Gate Arbiter 后续应决定：若 `human_review_required=true`，
是将其视为 `FAIL`、`BLOCKED`，还是只作为 `WARN`。在未确定该策略前，不能将
review-trigger 的结果误报为最终通过。

### 3.3 Runtime Artifact 与 Mailbox

当前 Entrix 会写入 runtime artifact、事件流和 mailbox 消息。这些输出是潜在的
集成点，但目前仓库内没有消费者、轮询器或确认机制。

因此它们目前只能被视为”可供外部 Harness 读取的被动证据”，不能视为已经完成的
Harness 集成。

### 3.4 现有输出与目标 Evidence Pack 的映射关系

为实现最小可用版本，Harness Orchestrator 可以直接复用 Entrix 现有输出作为证据来源。
以下映射关系明确了如何从现有组件构造目标 Evidence Pack：

| 现有输出 | 映射到 Evidence Pack 字段 | 来源组件 |
|---------|------------------------|----------|
| `FitnessReport.final_score` | `fitness.score_blocked` 判定输入 | `scoring.py:score_report()` |
| `FitnessReport.hard_gate_blocked` | `fitness.hard_gate_blocked` | `scoring.py:score_report()` |
| `entrix run --output report.json` | `fitness.report_path` | CLI 参数化输出 |
| `events.jsonl` 中的运行事件 | `collection_errors` 和审计日志来源 | `cli.py:_emit_runtime_fitness_event()` |
| `mailbox/fitness/new/*.json` | 实时事件通知（需改造成确认机制） | `cli.py:_write_runtime_fitness_mailbox_message()` |
| `review-trigger --json` 输出 | `review_trigger.report_path` 和 `review_trigger.human_review_required` | `review_trigger.py:evaluate_review_triggers()` |
| 每个 `MetricResult.output` | 失败项的原始输出摘要和 artifact 位置 | `engine.py:_run_metric_batch()` |

这种映射允许 Harness Orchestrator 在不修改 Entrix 核心逻辑的情况下，快速组装符合 schema 的 Evidence Pack。长期来看，runtime artifact 和 mailbox 机制需要从单向落盘升级为有确认、超时和重放保护的消息协议，但这不应阻塞 P0 最小可用版本的交付。

## 4. 目标架构

```text
Claude Runtime
  | Stop 请求（session_id, attempt_id, task_context）
  v
Stop Gate Adapter
  | 创建 Gate Attempt
  v
Harness Orchestrator
  | 调用 Entrix、测试、审查、必要的端到端检查
  v
Evidence Store
  | 不可变 evidence pack
  v
Gate Arbiter
  | PASS / FAIL / BLOCKED
  +--> PASS: Stop Gate Adapter 放行 Claude 结束
  +--> FAIL: Feedback Formatter -> Claude Runtime 恢复修改
  +--> BLOCKED: 请求人工或用户决策，不允许伪造 PASS
```

### 4.1 Stop Gate Adapter

责任：接入 Claude 所在运行环境提供的 Stop 生命周期钩子，并将 Stop 请求转换为
`GateAttempt`。

最低输入：

```json
{
  "schema_version": "gate-attempt.v1",
  "attempt_id": "uuid",
  "session_id": "runtime-specific-id",
  "task_id": "runtime-specific-id",
  "requested_at": "2026-08-14T00:00:00Z",
  "workspace": "absolute-path",
  "base_ref": "git-ref-or-null",
  "changed_files": ["relative/path"],
  "stop_reason": "agent_completed"
}
```

约束：Stop Gate Adapter 必须默认拒绝放行，直到收到与同一个 `attempt_id` 对应的
`PASS` 裁决。不能用上一次通过的结果放行新的 Stop 请求。

### 4.2 Harness Orchestrator

责任：使用与 Claude 相互独立的执行上下文收集证据。

最低检查集合：

1. 运行 Entrix fitness，并保存原始 JSON 报告；
2. 运行 `review-trigger`，并保存原始 JSON 报告；
3. 收集命令、环境、版本、开始和结束时间；
4. 记录执行错误，不把“检查未运行”转换为“检查通过”；
5. 将所有输入与输出绑定到当前 `attempt_id`。

“独立”至少意味着：Harness 不能接受 Claude 自述的“测试已通过”作为证据，
必须自行执行检查或读取具有可验证来源的 CI artifact。

### 4.3 Evidence Pack

每次 Stop 尝试都应生成一个不可变 evidence pack。建议最小结构如下：

```json
{
  "schema_version": "evidence-pack.v1",
  "attempt_id": "uuid",
  "collected_at": "2026-08-14T00:00:00Z",
  "revision": "git-sha-or-worktree-fingerprint",
  "fitness": {
    "status": "pass|fail|unknown|not_run",
    "report_path": "absolute-or-artifact-uri",
    "hard_gate_blocked": false,
    "score_blocked": false
  },
  "review_trigger": {
    "status": "pass|fail|unknown|not_run",
    "human_review_required": false,
    "report_path": "absolute-or-artifact-uri"
  },
  "collection_errors": []
}
```

Evidence pack 必须包含失败的原始输出位置或摘要。只保存布尔值会导致 Claude
无法定位问题，也让人工无法复核裁决。

### 4.4 Gate Arbiter

责任：仅依据 `GateAttempt`、evidence pack 和明确的策略生成唯一最终裁决。

裁决类型：

| 裁决 | 含义 | Stop 行为 |
| --- | --- | --- |
| `PASS` | 所有必需证据已收集且满足策略 | 放行 Claude 结束。 |
| `FAIL` | 已获得反例，例如硬门禁失败、测试失败、分数不足 | 拒绝 Stop，并把可操作失败项回传 Claude。 |
| `BLOCKED` | 无法获得必需证据，或策略要求人工决策 | 拒绝 Stop，并升级给用户或人工审查者。 |

基础策略：

- `fitness.hard_gate_blocked=true` 必须为 `FAIL`；
- `fitness.score_blocked=true` 必须为 `FAIL`；
- 必需检查 `not_run` 或 `unknown` 必须为 `BLOCKED`，不得为 `PASS`；
- `review_trigger.human_review_required=true` 的默认行为应为 `BLOCKED`，直到项目
  明确将其配置为允许自动通过或自动失败；
- evidence pack 对应的 revision 与当前工作区不一致时，必须重新收集证据。

### 4.5 Feedback Formatter

责任：将 `FAIL` 或 `BLOCKED` 转换为 Claude 可执行且对用户可审计的反馈。

`FAIL` 反馈最低应包括：

- 当前 `attempt_id`；
- 失败检查名称、类别和严重级别；
- 原始输出摘要和完整 artifact 位置；
- 需要满足的重新验证条件；
- 明确指令：继续修复，不允许结束任务。

示例：

```json
{
  "schema_version": "gate-feedback.v1",
  "attempt_id": "uuid",
  "verdict": "FAIL",
  "summary": "2 个硬门禁未通过，不能结束任务。",
  "findings": [
    {
      "source": "fitness",
      "metric": "pytest_pass",
      "severity": "hard_gate",
      "message": "测试命令退出码为 1",
      "artifact_path": ".../fitness-report.json"
    }
  ],
  "next_action": "修复以上问题后再次请求 Stop；系统将重新收集证据。"
}
```

#### 实现参考：现有 Reporter 与目标格式的区别

Entrix 现有 Reporter 组件主要面向"人类可读"的终端输出，而非"Claude 可执行"的工具调用格式：

| 现有组件 | 格式特点 | 适用场景 | 与目标 Feedback 的差距 |
|---------|---------|---------|---------------------|
| `TerminalReporter` | 终端文本、带 emoji 状态图标 | 开发者本地运行 | ❌ 非结构化，无法被 Claude 解析为可操作项 |
| `AsciiReporter` / `RichReporter` | 表格化分数卡 | CI 展示和报告 | ❌ 缺少具体失败 metric 的详细信息 |
| JSON 报告输出 | 完整的结构化数据 | 外部系统集成 | ✅ 可作为 Feedback Formatter 的输入源 |

当前 `MetricResult` 结构已包含所需的字段：
```python
# entrix/model.py:MetricResult
@dataclass
class MetricResult:
    metric_name: str
    passed: bool
    output: str          # 原始输出摘要
    tier: Tier
    hard_gate: bool     # 严重级别
    state: ResultState  # PASS/FAIL/UNKNOWN/WAIVED/SKIPPED
```

因此，Feedback Formatter 的实现可以基于现有的 JSON 报告和 `MetricResult` 结构，主要工作是将"数据报告格式"转换为"Claude 工具调用格式"，并补充 `attempt_id`、`next_action` 等编排层面的字段。不需要重新设计数据结构，重点是在格式转换层面增加语义化的指令和可操作性描述。

## 5. 状态机

```text
WORKING
  -> STOP_REQUESTED
  -> COLLECTING_EVIDENCE
  -> ARBITRATING
       -> PASSED      -> TERMINATED
       -> FAILED      -> FEEDBACK_DELIVERED -> WORKING
       -> BLOCKED     -> ESCALATED
```

状态约束：

- 只有 `PASSED` 可以进入 `TERMINATED`；
- `FAILED` 后不得直接终止，也不得自动标记任务完成；
- 每轮从 `WORKING` 进入 `STOP_REQUESTED` 都创建新的 `attempt_id`；
- 新的文件变更、提交或工作树指纹变化会使旧 evidence pack 失效；
- 连续失败达到阈值时可以升级为 `BLOCKED`，但不能绕过门禁。

## 6. 未完成工作清单

### P0：闭环最小可用版本

- [ ] 确认 Claude 目标运行环境支持的 Stop hook 或等价拦截 API；
- [ ] 实现 Stop Gate Adapter，能够接收会话和工作区上下文；
- [ ] 定义并持久化 `GateAttempt`、evidence pack、verdict 和 feedback schema；
- [ ] 实现 Harness Orchestrator，主动执行 Entrix fitness 与 review trigger；
- [ ] 实现 Gate Arbiter 的 `PASS`、`FAIL`、`BLOCKED` 规则；
- [ ] 实现 FAIL 回流，使 Claude 保持/恢复工作状态；
- [ ] 实现同一任务多次 Stop 的重新取证，不复用旧通过结果；
- [ ] 为完整 PASS、硬门禁 FAIL、证据缺失 BLOCKED、修复后 PASS 编写端到端测试。

### P1：证据可靠性与可运维性

- [ ] 为 evidence pack 增加工作区指纹、Git revision、工具版本和命令版本；
- [ ] 将 mailbox 从单向落盘改为有确认、超时和重放保护的消息协议；
- [ ] 为每个 attempt 提供可检索的审计日志和 artifact 索引；
- [ ] 处理并行 Stop 请求、重复 webhook 和进程崩溃恢复；
- [ ] 允许按项目策略配置 review trigger 的自动裁决方式；
- [ ] 增加重试上限和升级规则，避免无限修改循环。

### P2：现有 Entrix 运行时兼容性

- [ ] 将 runtime 根目录从硬编码 POSIX `/tmp` 改为跨平台临时目录策略；
- [ ] 为 Windows 指定可用 shell，或在 Windows 上显式拒绝不兼容的 shell metric；
- [ ] 让 runtime artifact、event 和 mailbox 写入失败时返回结构化 `BLOCKED`，而非仅抛出异常；
- [ ] 在 Windows、Linux 和 macOS 上执行包含 runtime 事件的测试矩阵。

## 7. 验收标准

以下场景全部满足，才可宣称该闭环已实现：

1. Claude 请求 Stop，Harness 自动运行独立检查；硬门禁失败时 Claude 无法结束；
2. FAIL 反馈中包含具体失败 metric、摘要和可访问 artifact；
3. Claude 修改后再次请求 Stop，Harness 对新工作区重新执行检查；
4. 旧 evidence pack 不能放行新 revision；
5. 所有必需证据通过时，Gate Arbiter 仅对当前 attempt 输出一个 `PASS`，随后允许结束；
6. 检查未运行、超时或无法读取 artifact 时，结果为 `BLOCKED`，不会误判为 `PASS`；
7. Stop hook、编排器和裁决器均有端到端测试，测试模拟至少一次 `FAIL -> 修改 -> PASS` 循环；
8. Linux、macOS、Windows 的支持范围被测试或明确声明，不能依赖未声明的 `/tmp` 或 `/bin/sh`。

## 8. 当前风险与待决策项

1. Claude 运行环境的 Stop hook 是否能真正阻断会话结束，需先以官方 API 或实际集成验证；
2. review trigger 触发后是自动失败还是必须人工确认，需由项目治理策略决定；
3. CI artifact 是否可作为独立证据，取决于它与当前工作区 revision 的绑定方式；
4. “需求完成”的语义验证不能仅靠 Entrix 的技术检查，需要决定是否接入测试、审查或用户验收层；
5. 本项目当前 runtime 输出使用 POSIX 路径，在 Windows 上已暴露兼容性问题，P0 集成前必须修复或明确限制平台。

## 9. 非目标

本阶段不包含以下事项：

- 让 Gate Arbiter 自动修改业务代码；
- 用模型主观判断替代可执行证据；
- 在证据缺失时为了改善体验而默认放行；
- 把人工审查要求伪装为机器裁决通过；
- 将 Entrix 的所有现有质量指标都改造成 Stop gate 的必要条件。

## 10. 实施前置条件

开始实现前必须确认：

1. 目标 Claude 运行时及其 Stop hook 的具体协议；
2. Harness 的宿主进程、部署位置和跨进程通信机制；
3. evidence/artifact 的保留期限与访问权限；
4. `review-trigger` 和人工审查的正式裁决策略；
5. 支持的操作系统与 shell 运行策略。
