# 会话感知 Stop Gate 生命周期设计

> 日期：2026-08-24
>
> 状态：已确认，等待实施计划
>
> 范围：Stop Gate 生命周期、会话变更归属、Review Trigger 数据一致性、Hook 集成与诊断

## 1. 背景

Claude Code 的 `Stop` 事件只表示模型准备结束当前回复，并不表示用户任务已经完成。现有 Entrix Stop Gate 在每次 `Stop` 时读取仓库级 phase 和整个工作区的 Git 变更，再据此推断是否应执行 Harness。这会混淆以下场景：

- 普通对话与真正的编码任务完成；
- 实现过程中的澄清、等待用户确认与最终交付；
- 会话开始前已有的未提交修改与当前会话产生的修改；
- 同一工作区中其他并发会话的修改；
- 当前会话已经提交、因而不再出现在工作区 diff 中的修改。

此外，Entrix Review Trigger producer 会重新扫描整个仓库 diff，没有严格消费 Stop Gate 已经构造的变更上下文。这会让生命周期判断、Fitness、Review Trigger、Diff Stats 和 verdict 缓存基于不同的数据集合。

## 2. 目标

本设计采用“明确任务完成事件 + 会话变更账本 + `Stop` 兼容兜底”的混合策略，目标如下：

1. 普通对话、规划和实现中途提问不得触发重门禁。
2. `TaskCompleted` 是权威完成事件；普通编码请求通过显式 `ready` 状态进入完成路径。
3. Gate 只审查当前 session、当前任务代次实际产生或修改的文件。
4. Fitness、Review Trigger、Diff Stats 和 verdict 缓存消费同一个冻结 `ChangeSet`。
5. `stop_hook_active=true` 必须立即放行，杜绝 Stop hook 无限阻断。
6. 配置错误、状态错误和归属缺口应可诊断、可恢复，并且不污染项目仓库。
7. 保持 Windows、Linux 和 macOS 上的行为及 Hook 契约一致。

## 3. 非目标

本阶段不包含：

- `entrix/cli.py` 的全面拆分；
- 结构分析适配器的大规模重构；
- 与 Stop Gate 无关的类型覆盖扩张；
- 基于自然语言、最后一条回复或关键词的任务完成分类器；
- 将其他 session 或会话开始前的仓库修改纳入当前 Gate。

这些项目进入后续优化清单，避免扩大第一阶段的行为变更范围。

## 4. 核心决策

### 4.1 完成信号

`Stop` 不再自行推断任务完成。只有以下事件可以进入完成路径：

- Claude Code `TaskCompleted` hook；
- Agent 显式执行 `entrix phase ready --repo <path> --session-id <id>`。

当项目存在 `harness.yaml` 时，`UserPromptSubmit` hook 向 Agent 注入当前 session 对应的完成命令。该提示属于 Agent 上下文，不作为用户可见的功能说明。Agent 只在准备交付最终结果时执行该命令。

### 4.2 会话隔离

所有生命周期状态都以 `workspace + session_id + generation` 为作用域，保存在 Entrix 用户状态目录。运行时不再回退读取 workspace 级 phase。缺少 session id 的 phase 修改命令应返回迁移提示，不得创建影响所有会话的共享标记。

### 4.3 单一变更事实来源

会话账本生成的 `ChangeSet` 是完成门禁的唯一变更事实来源。Harness producer 不得在执行过程中重新扫描全仓库来替换或扩充该文件集。

## 5. 生命周期状态机

```text
observing -> planning
    |
    v
implementing -> ready -> validating -> passed
    ^             |          |
    |             |          v
    +-------------+------- blocked
```

状态语义：

| 状态 | 含义 | `Stop` 行为 |
| --- | --- | --- |
| `observing` | 当前任务尚无实现改动 | 放行 |
| `planning` | 规划、设计或等待批准 | 放行 |
| `implementing` | 已有当前任务改动，但尚未声明完成 | 放行 |
| `ready` | Agent 明确准备完成 | 执行兼容 Gate |
| `validating` | Gate 正在执行 | 相同尝试不得并发重复执行 |
| `blocked` | 最近一次 Gate 未通过 | 等待同 session 修复并重新 `ready` |
| `passed` | 当前任务代次已完成 | 放行；下一任务创建新代次 |

事件转换：

- `SessionStart` 创建 session 账本，初始状态为 `observing`。
- `UserPromptSubmit` 在前一任务已终止时创建新 generation；若任务仍在 `planning`、`implementing` 或 `blocked`，则继续原 generation。
- 成功的写入型 `PostToolUse` 在确认文件变化后进入 `implementing`。
- `TaskCompleted` 或显式 `ready` 进入 `ready`。
- Gate 开始时进入 `validating`，结束后进入 `passed` 或 `blocked`。
- `SessionEnd` 关闭 session，并按保留策略清理临时基线。

`stop_hook_active=true` 的检查位于所有配置发现、状态读取和 Gate 调用之前，命中后立即返回成功且不输出 block decision。

## 6. Hook 架构

插件注册以下 Hook：

| Hook | 职责 | 失败是否阻断 |
| --- | --- | --- |
| `SessionStart` | 创建 session 状态 | 否，记录诊断 |
| `UserPromptSubmit` | 开始/继续 generation，注入完成命令 | 否，记录诊断 |
| `PreToolUse` | 为可能写入的工具建立调用前快照 | 否，记录 tracking gap |
| `PostToolUse` | 对比调用前后状态并写入变更事件 | 否，记录 tracking gap |
| `TaskCompleted` | 冻结 `ChangeSet` 并执行权威 Gate | 是，使用事件对应的阻断契约 |
| `Stop` | 仅为显式 `ready` 提供兼容 Gate | 仅完成路径 fail-closed |
| `SessionEnd` | 关闭状态、清理过期快照 | 否 |

每个 Hook 由统一 lifecycle dispatcher 读取标准输入，再交给事件适配器。事件适配器负责输出 Claude Code 对应 Hook 的合法响应，避免把 `Stop` 的 `decision: block` 契约错误复用到其他事件。

没有 `harness.yaml` 时，所有 Hook 都应快速成功返回，不创建生命周期状态，也不运行 Git 子进程。

## 7. Session Activity Ledger

### 7.1 逻辑模型

账本至少包含：

```text
SessionLedger
  schema_version
  workspace
  session_id
  generation
  lifecycle_state
  ready_source
  branch
  baseline_head
  changed_files
  tracking_gaps
  last_verdict
  created_at / updated_at / expires_at
```

每个变更文件记录：

```text
SessionFileChange
  relative_path
  operation: add | modify | delete | rename
  baseline_fingerprint
  current_fingerprint
  baseline_snapshot
  binary
  added_lines / deleted_lines
  provenance_events
```

状态文件、临时快照、verdict 和 evidence 继续保存在 `ENTRIX_STATE_DIR` 或平台默认用户状态目录中，不写入 `.harness/runtime`。写入使用原子替换和 session 级并发保护；损坏或版本不兼容的状态不得静默解释为有效数据。

### 7.2 任务代次

一个 Claude session 可以包含多个用户任务。`generation` 防止前一任务的文件和 verdict 被后续普通对话复用：

- 前一代次为 `passed` 或已关闭时，下一次 `UserPromptSubmit` 创建新代次；
- 澄清回复发生在活动任务中时继续原代次；
- Gate 失败后的修复继续原代次；
- 缓存键必须包含 generation。

## 8. 文件归属算法

### 8.1 结构化写入工具

对于 Edit、Write、NotebookEdit 等具有明确路径的工具：

1. `PreToolUse` 验证并规范化 workspace 内路径，记录调用前指纹和必要的首触基线；
2. `PostToolUse` 读取调用后状态；
3. 只有内容、存在性或规范化路径发生变化时才写入 session 变更事件。

路径解析必须拒绝 workspace 逃逸。符号链接解析后指向 workspace 外部时不得纳入，也不得为其保存内容快照。

### 8.2 Shell 工具

Shell 命令可能同时格式化、生成、删除、重命名或提交多个文件。调用前后记录：

- 当前 HEAD；
- Git 状态候选集合；
- HEAD 变化涉及的路径；
- 候选文件的存在性和内容指纹。

候选集合取调用前 dirty、调用后 dirty、HEAD 区间变化和工具显式路径的并集，再通过调用前后指纹确认实际净变化。这样可以覆盖“修改后在同一命令中提交”的场景，同时排除调用前已 dirty 但本次没有变化的文件。

### 8.3 基线和 diff 统计

文件第一次被当前任务修改前保存受限基线。文本文件使用该基线与最终内容计算本任务净增删行，避免依赖当前 `git diff HEAD`。二进制文件记录内容指纹和二进制标志，不伪造行统计。

快照设置单文件和任务总量上限。超过上限时记录 `stats_unavailable` tracking gap；完成路径不得回退读取全仓库 diff。是否阻断由完成路径的完整性规则决定，并给出明确恢复方式。

### 8.4 不可证明归属

无法证明由当前 session 修改的文件不进入 `ChangeSet`。系统记录 reason code、事件和候选路径，供 `entrix status --json` 与 `entrix doctor` 展示。该规则优先保证会话隔离，不以“可能漏检”为由重新混入其他会话的修改。

## 9. Gate 数据流

```text
Session Ledger
  -> freeze ChangeSet
  -> HarnessRunContext
       -> Fitness Producer
       -> Review Trigger Producer
       -> Diff Stats Producer
  -> GateEngine
  -> Verdict + Evidence
```

具体约束：

- `HarnessRunContext.changed_files` 来自冻结的 session `ChangeSet`；
- Review Trigger producer 不再调用 `collect_changed_files()`；
- Diff Stats producer 使用 `ChangeSet` 的 session 净变化统计；
- Fitness producer 保持使用 context 中的 changed files；
- producer 可以缩小适用范围，但不得扩大到 `ChangeSet` 外；
- 当前 session 没有文件变化时，完成事件直接记录 no-op pass，不运行重门禁；
- 不再使用硬编码扩展名列表跳过文档或配置文件，适用性由 `harness.yaml` 条件决定。

## 10. Verdict 缓存与复验

缓存指纹至少包含：

- session id 与 generation；
- 冻结 `ChangeSet` 中每个文件的最终指纹或删除标志；
- branch、baseline HEAD 和有效 base ref；
- Harness 配置内容哈希；
- `when` 条件依赖的环境指纹；
- lifecycle/cache schema 版本。

本 session 后续产生任何文件净变化、配置变化、分支变化或环境条件变化都会使缓存失效。失败缓存只可用于解释相同快照，不得授权其他 generation 或其他 session。

## 11. 错误和恢复策略

### 11.1 非完成路径

普通对话和开发过程以不中断为原则：tracking hook 失败时返回成功，同时把错误写入当前 session 的 `tracking_gaps`。不得在每个 `Stop` 上重复显示同一错误。

### 11.2 完成路径

`ready` 或 `TaskCompleted` 后采用 fail-closed：

- 未信任 Harness 配置：阻断并提示 `entrix trust`；
- tracking gap 导致无法形成完整 `ChangeSet`：阻断并给出状态检查/重置命令；
- Harness 配置错误、执行异常或超时：阻断并返回结构化原因；
- Gate 未通过：阻断并返回 evidence 和修复摘要；
- `stop_hook_active=true`：即使前次失败也立即放行，遵守 Claude Code 防递归要求。

`entrix stop-gate retry` 只清理当前 generation 的 verdict 和 validating 状态，保留已确认的文件归属。需要完全丢弃账本时使用独立、显式的 lifecycle reset 操作。

## 12. 诊断与可观测性

`entrix status --json` 增加：

- session id、generation 和 lifecycle state；
- ready 来源和时间；
- 当前 session 归属文件及操作类型；
- tracking gaps 和 reason code；
- 最后 verdict、缓存指纹摘要和 evidence 路径。

`entrix doctor` 增加：

- 插件多事件 Hook 是否完整；
- 状态目录是否可读写；
- lifecycle schema 是否兼容；
- 是否残留过期 session、临时快照或 validating 状态；
- legacy workspace phase 的迁移提示。

正常放行保持 stdout 为空。诊断日志写入 stderr，并使用稳定 reason code，便于测试和问题定位。

## 13. 兼容和迁移

- 保留 `entrix stop-gate` 作为 Hook/手工调试入口，但没有活动 `ready` 状态时默认放行；
- `phase planning`、`phase implementation` 迁移到 session lifecycle；新增 `phase ready`；
- phase 命令缺少 session id 时不再写 workspace 共享状态，而是返回迁移说明；
- 清理或忽略 `.harness/runtime/phase.json`，不得将其作为兼容回退；
- 同步更新源码 Hook 配置、插件 manifest、内置 skill、README、命令参考和 Stop Gate 指南；
- 保持 standalone binary launcher 作为所有插件 Hook 的唯一执行入口。

## 14. 安全与资源约束

- 状态和快照路径由 workspace/session 哈希派生，不直接拼接不可信标识；
- 快照只允许 workspace 内文件，限制单文件大小、任务总大小和保留时间；
- state JSON 解析执行 schema、类型、workspace 和 session 一致性校验；
- Hook 不执行来自 payload 的命令文本；仅把 payload 作为观测数据；
- 没有 Harness 配置的项目不运行 Git 子进程；
- completion Gate 延续现有总超时，tracking hooks 使用更短独立超时；
- SessionEnd 和 TTL 清理只作用于已解析并验证位于 Entrix 状态根目录内的目标。

## 15. 测试策略

采用 TDD，每个行为变更先添加失败测试。测试层次包括：

1. 生命周期状态机和 generation 单元测试；
2. session ledger schema、原子写入、损坏恢复和过期清理测试；
3. 结构化工具及 Shell 变更归属测试；
4. dirty 基线、并发 session、提交后 clean worktree、删除和重命名测试；
5. 各 Claude Hook 的输入/输出契约测试；
6. Review Trigger、Fitness、Diff Stats 只消费 session `ChangeSet` 的集成测试；
7. verdict 缓存隔离与失效测试；
8. Windows 路径、符号链接逃逸、快照上限和状态损坏测试；
9. `stop_hook_active=true` 的防循环回归测试；
10. CLI status、doctor、retry 和 phase 迁移测试。

## 16. 验收标准

| 场景 | 预期结果 |
| --- | --- |
| 普通对话、无修改 | `Stop` 安静放行 |
| 规划或实现中途提问 | `Stop` 放行 |
| session 有修改但未 `ready` | `Stop` 放行 |
| session 有修改且 `ready` | 执行 Gate |
| 收到 `TaskCompleted` | 执行 Gate |
| 会话开始前已有 dirty 文件 | 不纳入 `ChangeSet` |
| 其他并发 session 修改文件 | 不纳入 `ChangeSet` |
| 本 session 修改后执行 commit | 修改仍纳入 Gate |
| Review Trigger 执行 | 只消费 session `ChangeSet` |
| Gate 失败后 `stop_hook_active=true` | 放行，不形成阻断循环 |
| 完成时存在不可恢复 tracking gap | 明确阻断并给出恢复命令 |
| session 文件或 Harness 配置变化 | 旧 verdict 缓存失效 |

最终质量命令：

```text
ruff check .
ruff format --check .
mypy
pytest -q --junitxml=.artifacts/pytest.xml
python -m build --no-isolation
python -m entrix harness validate harness.yaml
```

## 17. 后续优化清单

第一阶段完成后再独立评估：

- 按 `run`、`harness`、`graph`、`release`、`hook` 继续拆分 `entrix/cli.py`；
- 扩大其余 Python 模块的 mypy 严格覆盖；
- 继续拆分结构分析适配器；
- 增加 session ledger 的长期统计和性能观测；
- 评估其他 Agent/IDE Hook 平台的统一 lifecycle adapter。
