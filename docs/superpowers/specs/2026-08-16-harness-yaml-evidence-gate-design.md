# YAML-Driven Evidence Collection and Gate Arbitration — MVP Design

- Status: Approved
- Date: 2026-08-16
- Related ADR: [ADR 0002: YAML-Driven Evidence Collection and Gate Arbitration for Claude Stop Hook](../../../adr/0002-harness-yaml-evidence-gate.md)

## Context

Entrix 已经实现了一个 `stop-gate` 子系统，用于在 Claude Code `Stop` 请求时执行质量门禁。当前实现的问题是：

1. **Evidence producer 是隐式且硬编码的**：`EvidenceCollector` 直接调用 `run_fitness_report` 和 `evaluate_review_triggers`，无法通过配置新增 producer。
2. **Gate 规则是硬编码的 Python 逻辑**：`GateArbiter` 只理解 fitness 的 `hard_gate_blocked`、`score_blocked` 和 review-trigger 的 `human_review_required`，项目无法自定义停止策略。

本设计文档定义一个最小可用版本（MVP），把证据收集和门禁裁决改造成由 `harness.yaml` 驱动的可配置层。

## Goals

- 引入 `harness.yaml` 作为项目级停止策略配置。
- 支持通用 `command` producer，能执行任意命令并用 `exit_code` 或 `regex` 解析结果。
- 支持内置 producer：`entrix-fitness` 和 `entrix-review-trigger`。
- 支持声明式 gate 规则，表达式 DSL 包含 `==`、`!=`、比较、算术、`in`、`and`/`or`/`not`、括号。
- 支持条件激活：`files_exist`、`changed_any`、`branch`、`env`。
- 将 evidence bundle 持久化到 `.harness/evidence/<task-id>/<timestamp>-bundle.json`。
- 提供 CLI：`entrix harness validate`、`entrix harness run`。
- 保持 `entrix stop-gate` 的 hook 契约不变；无 `harness.yaml` 时回退到旧逻辑。

## Non-Goals

- 不支持 JUnit/SARIF 等复杂 parser（后续迭代）。
- 不支持 plugin registry / entry-point 发现（后续迭代，见「未来工作」）。
- 不支持 remote evidence 摄入、gate policy 继承、time-windowed 条件（后续迭代）。
- 不支持 `entrix harness replay` 命令（后续迭代）。

## Design Overview

新增 `entrix/harness/` 包作为通用的 Evidence + Gate 层；`entrix/stop_gate/` 只保留 Stop hook 专属代码，通过 `HarnessRunner` 调用 harness 层。

```text
entrix/harness/              # 新增：可复用的 Evidence + Gate 层
├── config.py                # harness.yaml 加载与校验
├── conditions.py            # when 谓词求值
├── evidence.py              # Evidence / EvidenceBundle 数据类
├── store.py                 # evidence bundle 磁盘读写
├── engine.py                # EvidenceEngine：编排 producer
├── producers/
│   ├── base.py              # Producer 抽象
│   ├── command.py           # 通用命令 producer
│   └── builtin.py           # entrix-fitness、entrix-review-trigger
└── gate/
    ├── policy.py            # GatePolicy / Severity
    ├── dsl.py               # 表达式解析与求值
    └── arbiter.py           # GateEngine 裁决

entrix/stop_gate/            # 现有：仅保留 hook 专属代码
├── hook.py                  # CLI 入口、payload 读取、激活判断
├── adapter.py               # payload → HarnessRunContext
├── engine.py                # 调用 HarnessRunner，管理 attempt 状态
├── state_manager.py         # 尝试状态持久化
├── formatter.py             # 把 Verdict 格式化成 Claude 反馈
├── model.py                 # Verdict / StopDecision / GateAttempt
└── runner.py                # 新增：HarnessRunner，串联 harness 层
```

### 关键边界

- `harness/` 不依赖 `stop_gate/`，可被 CLI、MCP、CI 复用。
- `stop_gate/` 负责：读取 hook 载荷、判断激活方式、格式化最终反馈、状态管理。
- 存在 `harness.yaml` 时完全由 harness 层接管；不存在时走旧逻辑。

## Module Responsibilities

### `harness/config.py`

加载并校验 `harness.yaml`。MVP 支持：

- `version`: 必须为 `"harness/v1"`。
- `when`: 全局激活条件。
- `evidence_producers`: producer 列表。
- `gate_policies`: gate 规则列表。

校验失败时在校验阶段明确报错。

### `harness/conditions.py`

实现 `when` 谓词求值。MVP 支持：

- `files_exist`: 文件存在性检查。
- `changed_any`: 变更文件匹配任一 glob。
- `branch`: 分支 include/exclude 模式。
- `env`: 环境变量精确匹配。

同个 `when` 块内所有谓词为 AND 语义；列表内为 OR 语义。依赖 git 的谓词在 git 不可用时返回 `False`。

### `harness/evidence.py`

定义标准 evidence 数据类：

```python
@dataclass
class Evidence:
    schema_version: str = "evidence/v1"
    id: str = ""
    type: str = ""              # test / lint / typecheck / diff / custom
    name: str = ""
    status: str = ""            # pass / fail / skipped / error / timeout
    producer: str = ""
    task_id: str = ""
    started_at: str = ""        # ISO-8601 UTC
    duration_ms: int = 0
    summary: dict = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

@dataclass
class EvidenceBundle:
    schema_version: str = "evidence-bundle/v1"
    task_id: str = ""
    attempt_id: str = ""
    collected_at: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    collection_errors: list[dict] = field(default_factory=list)
```

### `harness/store.py`

把 `EvidenceBundle` 写入 `.harness/evidence/<task-id>/<timestamp>-bundle.json`。保存失败不影响裁决，仅记录 `collection_errors`。

### `harness/engine.py`

`EvidenceEngine` 编排 producer：

1. 求值全局 `when`。
2. 对每个 producer 求值自身 `when`。
3. 并行执行激活的 producers。
4. 收集并返回 `EvidenceBundle`。

单个 producer 失败不中断其他 producer。

### `harness/producers/`

- `base.py`: `Producer` 协议，`run(context) -> Evidence`。
- `command.py`: `CommandProducer` 执行命令，支持 `exit_code` 和 `regex` parser。
- `builtin.py`: `EntrixFitnessProducer`、`EntrixReviewTriggerProducer`、`DiffStatsProducer`。

### `harness/gate/`

- `policy.py`: `GatePolicy`、`GateRule`、`Severity`。
- `dsl.py`: 表达式解析器。MVP 支持 `==`、`!=`、`<`、`<=`、`>`、`>=`、算术（`+ - * /`）、`in`、`and`/`or`/`not`、显式括号。
- `arbiter.py`: `GateEngine` 对所有 gate 求值，返回 `PASS` / `FAIL` / `BLOCKED`。

Severity 语义：

- `hard`: 条件为假 → `FAIL`。
- `soft`: 条件为假 → 警告，但仍 `PASS`。
- `advisory`: 仅记录，不影响结果。
- `blocked`: 条件为真 → `BLOCKED`（注意与 `hard` 的触发方向相反）。

## `harness.yaml` MVP Schema

```yaml
version: "harness/v1"

# 全局激活条件（可选）
when:
  branch:
    exclude:
      - docs/**

# Evidence producers
evidence_producers:
  - id: typecheck
    type: typecheck
    name: TypeScript type check
    command: npm run typecheck
    producer: tsc
    parser:
      type: exit_code

  - id: unit-test
    type: test
    name: Unit tests
    command: pytest tests -q
    producer: pytest
    timeout_seconds: 120
    when:
      changed_any:
        - src/**
        - tests/**
    parser:
      type: regex
      pattern: 'passed=(?P<passed>\d+), failed=(?P<failed>\d+)'
    artifacts:
      - type: junit
        path: junit.xml

  - id: diff-stats
    type: diff
    name: Git diff statistics
    builtin: diff-stats

# Gate policies
gate_policies:
  - name: typecheck passes
    severity: hard
    rule:
      evidence_id: typecheck
      condition: status == "pass"

  - name: no test failures
    severity: hard
    rule:
      evidence_id: unit-test
      condition: summary.failed == 0

  - name: diff too large
    severity: blocked
    rule:
      evidence_id: diff-stats
      condition: summary.added_lines > 500
    action: require_human_review
```

## Execution Flow

### `entrix stop-gate`

```
Claude Stop
    ↓
entrix stop-gate (hook.py)
    ↓
检查 harness.yaml 是否存在
    ├─ 不存在 → 旧逻辑（fitness + review-trigger）
    └─ 存在   → 新逻辑
        ↓
StopGateAdapter 构建 HarnessRunContext
        ↓
HarnessRunner.run(context)
    ├── EvidenceEngine.collect()
    │       ├── 全局 when
    │       ├── 各 producer when
    │       ├── 并行执行 producers
    │       └── EvidenceBundle
    ├── EvidenceStore.save(bundle)
    ├── GateEngine.arbitrate(bundle)
    │       └── Verdict (PASS / FAIL / BLOCKED)
    └── Verdict
        ↓
FeedbackFormatter 生成反馈
        ↓
输出 decision / reason
```

### `entrix harness validate`

仅加载并校验 `harness.yaml`，不执行 producer。

### `entrix harness run`

读取当前目录 `harness.yaml`，执行完整 collect → store → arbitrate 流程，输出 JSON 或文本报告。

## Error Handling

| 场景 | 行为 |
| --- | --- |
| Producer 命令超时 | `status = "timeout"` |
| 命令返回非 0（exit_code parser） | `status = "fail"` |
| 命令无法执行 | `status = "error"`，记录异常 |
| regex 解析失败 | `status = "error"`，追加 collection_errors |
| Gate 表达式语法错误 | `validate` 阶段报错 |
| Gate 运行时引用缺失字段 | 视为 error，hard/block  gate 失败 |
| 保存 bundle 失败 | 不影响裁决，记录 collection_errors |
| 无 harness.yaml | stop-gate 走旧逻辑，直接放行或旧裁决 |
| 不支持的 harness.yaml version | 报错并阻止停止 |

## Testing Strategy

### 单元测试

- `tests/harness/test_config.py`: 配置加载与校验。
- `tests/harness/test_conditions.py`: when 谓词组合。
- `tests/harness/test_evidence.py`: 数据类序列化。
- `tests/harness/test_store.py`: bundle 持久化。
- `tests/harness/test_command_producer.py`: exit_code / regex parser，超时。
- `tests/harness/test_gate_dsl.py`: 表达式解析与求值。
- `tests/harness/test_arbiter.py`: 静态 evidence → verdict。

### 集成测试

- `tests/harness/test_engine.py`: 端到端运行最小 harness.yaml。
- `tests/stop_gate/test_harness_integration.py`: stop-gate 在存在/不存在 harness.yaml 时的路由。

### 不测试（MVP）

- 真实 pytest / tsc 调用（用 fixture 命令替代）。
- 大规模并行性能。
- plugin registry。

## Backwards Compatibility

- 仓库无 `harness.yaml` 时，`entrix stop-gate` 保持现有行为不变。
- 存在 `harness.yaml` 时，完全由 harness 层接管，不再自动注入旧 fitness/review-trigger。
- 旧的 `docs/fitness/*.md` 和 `docs/fitness/review-triggers.yaml` 继续被内置 producer 支持，但必须在 `harness.yaml` 中显式声明才会运行。

## Future Work

- **Plugin registry（方案 C）**: 抽象 `ProducerRegistry`，支持 entry-point 发现的第三方 producer。
- **复杂 parser**: JUnit、SARIF、JSON path。
- **`entrix harness replay`**: 读取已保存的 bundle 重新裁决。
- **Remote evidence**: CI 系统向 evidence store 发布结果。
- **条件扩展**: `changed_all`、`changed_none`、`changed_in_last_days`、基于其他 evidence 的 `evidence` 谓词。
- **Policy 继承**: monorepo 共享基础 gate policy。

## Decisions Made

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 架构方案 | 方案 A：分层架构 | 边界清晰，易测试，支持后续扩展 |
| 表达式 DSL | 接近 ADR 完整版 | 覆盖常见 gate 规则 |
| 条件谓词 | `files_exist`、`changed_any`、`branch`、`env` | 覆盖主流场景 |
| Command parser | `exit_code` + `regex` | JUnit 实现成本高，延后 |
| Evidence 持久化 | 基础 JSON 落盘 | 可审计，为 replay 打基础 |
| CLI | `validate` + `run` | 满足调试需求 |
| 向后兼容 | harness.yaml 存在即接管 | 语义清晰 |
| Plugin registry | 后续迭代 | MVP 避免过度设计 |
