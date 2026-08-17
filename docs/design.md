# Entrix Harness/Stop Gate 修复设计

## 目标

修复当前审查发现的运行时安全问题和架构断链，使 `harness.yaml` 成为可实际执行的项目级门禁配置，同时保留没有该配置时的旧 Stop Gate 行为。

本次范围包含：

- 接通 `harness.yaml -> stop-gate -> HarnessRunner -> EvidenceEngine -> GateEngine` 主链路。
- 在配置加载边界把 YAML 配置转换为裁决器使用的领域模型，并拒绝非法配置。
- 修复 Entrix fitness/review-trigger 内置 producer 的现有 API 适配。
- 修复 DSL 的列表、整数转换、完整输入消费和错误语义。
- 修复 pytest 测试模块收集冲突，并让新增/受影响测试在 Windows 与 Linux 上使用同一套写法。
- 补齐 Ruff/Mypy/Pre-commit 基线配置所需的最小范围。

不包含 `cli.py` 的大规模拆分、远程 evidence、plugin registry 或 replay 命令。

## 架构边界

```text
Claude Stop Hook
       |
       v
stop_gate.hook
  |-- harness.yaml 存在 --> HarnessRunner
  |                          |--> EvidenceEngine
  |                          |      |--> CommandProducer
  |                          |      `--> Builtin Producers
  |                          `--> GateEngine
  |
  `-- harness.yaml 不存在 --> StopGateEngine (legacy collector/arbiter)

两条路径都返回统一的 hook 输出：
exit 0 + 空 stdout = allow
exit 0 + {"decision":"block", "reason":"..."} = block
```

### 配置与领域模型

`harness.config.load_harness_config()` 负责 YAML 解析、字段校验和领域转换：

- `severity` 转成 `Severity` 枚举。
- `rule` 转成 `GateRule`，必须恰好指定 `evidence_id` 或 `evidence_type`。
- producer 的 id 必须非空且唯一；command producer 必须有 command；builtin 必须在注册表中。
- parser 仅接受 `exit_code` 和 `regex`，regex 必须有 pattern。
- DSL 在 validate 阶段完成语法和字段引用的结构校验，运行期错误产生失败 evidence，不得静默放行。

CLI 与 Stop Gate 只接收已经转换后的 `HarnessConfig`，不得把 `GatePolicyConfig` 直接传给 `GateEngine`。

### Stop hook 路由

增加一个纯函数定位配置：优先 `<workspace>/harness.yaml`，其次 `<workspace>/.harness/harness.yaml`。存在配置时，hook 将 Claude payload 转换成 `HarnessRunContext` 并调用 `HarnessRunner`；不存在时保持旧 `StopGateAdapter` 路径。

Harness 路径不创建 `StopGateAdapter`，避免新层为了适配 context 初始化 legacy engine，也避免 `harness -> stop_gate` 的反向依赖。

`HarnessRunner` 的异常必须转成阻断 decision；只有未配置 harness 时才使用旧 collector/arbiter。producer 命令失败、超时、解析错误都生成明确的非 pass 状态，不能因收集异常返回 PASS。

### 内置 producer 适配

- `EntrixFitnessProducer` 调用 `entrix.engine.run_fitness_report(project_root, GovernancePolicy(), get_project_preset(), ...)`，把 `FitnessReport` 转为标准 evidence summary。
- `EntrixReviewTriggerProducer` 调用 `entrix.review_trigger` 的实际加载、diff 收集和评估 API。
- producer 只把标准字段提供给 GateEngine；工具原始 stdout 仅放在 `raw`。

### DSL 约束

保留当前递归下降解析器，增加：

- `in ["pass", "skipped"]` 列表字面量。
- `int(value)` 的白名单转换函数，用于 regex 产生的数字字符串。
- 解析结束必须只剩空白字符，否则报语法错误。
- 禁止 `eval`、属性访问以外的任意 Python 执行。

### 测试与平台

- 测试目录使用唯一模块名或 `--import-mode=importlib`，默认 `pytest` 必须能完成收集。
- 临时目录统一使用 pytest `tmp_path`，不使用硬编码 `/tmp`。
- shell producer 的超时测试使用当前 Python 解释器和跨平台短 sleep 命令。
- 每个缺陷先有失败回归测试，再实现最小修复。

## 错误与兼容性

| 场景 | 行为 |
| --- | --- |
| 无 harness 配置 | 使用 legacy Stop Gate |
| 配置版本/字段非法 | validate 失败；Stop hook 阻断并返回配置错误 |
| producer 失败/超时/解析失败 | evidence 状态为 `error`/`timeout`，hard gate 不得 PASS |
| gate 引用不存在 evidence | hard 为 FAIL，blocked 为 BLOCKED |
| 保存 evidence 失败 | 保留裁决结果，同时在 bundle 的 `collection_errors` 记录 |
| Stop hook 内部未预期异常 | 按现有 hook 契约输出错误并阻断；不静默放行 |

## 验收标准

1. `harness run` 的 hard gate 失败返回非 pass 状态和非零退出码。
2. 有效 `harness.yaml` 的 Stop hook 确实调用 HarnessRunner；无配置仍调用旧路径。
3. 两个内置 producer 可在当前仓库 API 上运行，不出现 `ModuleNotFoundError`。
4. DSL 支持设计文档声明的列表、`int` 和表达式尾部校验。
5. 默认 `pytest` 能完成全量测试收集；受影响测试在 Windows/Linux 上不依赖 `/tmp`。
6. `ruff check .`、`mypy .`（若环境已安装）和 `python -m build` 的结果被记录。

---

# Entrix 单文件 Harness 配置设计

## 决策

Entrix 的项目级质量配置统一为仓库根目录的 `harness.yaml`。`entrix init` 在初始化 MCP 配置的同时生成该文件。Fitness 维度、指标和 review trigger 规则都以内联 YAML 保存；运行时不再读取 `docs/fitness/`、`manifest.yaml` 或 `review-triggers.yaml`，也不提供旧格式兼容路径。

## 数据流

```text
entrix init
  -> .mcp.json + harness.yaml（默认质量策略）

entrix run / review-trigger / harness run / stop-gate
  -> load_harness_config(harness.yaml)
  -> inline Fitness dimensions / review rules
  -> FitnessReport / ReviewTriggerReport / EvidenceBundle
  -> GateEngine verdict
```

`harness.yaml` 是唯一事实来源。缺少该文件的项目被视为未配置：`stop-gate` 放行，其他需要质量规则的 CLI 命令返回清晰的配置缺失错误。

## 配置结构

顶级 `fitness.dimensions` 保留现有 `Dimension`/`Metric` 的全部可执行字段，例如 `weight`、`tier`、`threshold`、`command`、`pattern`、`hard_gate`、`execution_scope`、`run_when_changed` 和元数据。顶级 `review_triggers.rules` 保留原规则匹配字段。Harness loader 负责把两部分分别转换为领域 `Dimension` 与 `ReviewTriggerRule`，不保留中间文件或路径引用。

内置 `entrix-fitness` producer 使用已解析的 `Dimension` 列表执行；内置 `entrix-review-trigger` producer 使用已解析的规则列表评估。两者不再根据 `repo_root/docs/fitness` 推导配置。

## 初始化与覆盖规则

`entrix init`：

1. 保持现有 `.mcp.json` 写入行为。
2. 创建 `harness.yaml`，预置当前项目的 Ruff、debug print、pytest、CLI help、构建、observability 和 performance 策略，以及 review trigger 和 Stop Gate 规则。
3. 若 `harness.yaml` 已存在，默认报错且不改写；显式 `--force` 才允许以默认模板重建。

初始化不会创建 `docs/fitness/` 或任意旁路质量配置文件。

## 命令可发现性

根命令 `entrix --help` 增加按任务分组的中文命令导览，至少覆盖：初始化（`init`）、执行 Fitness（`run`）、配置校验（`harness validate`）、完整 Harness 裁决（`harness run`）、审查触发检查（`review-trigger`）、Stop Hook（`stop-gate`）以及 MCP 服务（`serve`）。每项给出一句用途和一个最短可运行示例。

`entrix init` 成功后打印固定的“下一步”清单：`harness validate` 用于检查生成配置，`run` 用于执行 Fitness，`harness run` 用于收集 evidence 并裁决，`stop-gate` 用于供 Claude Hook 调用。提示不执行任何检查、不依赖终端颜色，也不输出与机器路径无关的环境假设。

## 迁移边界

本次变更为有意的不兼容变更：删除当前仓库的 `docs/fitness/`，删除相关 fixture 副本，并移除 Markdown fitness loader、manifest 发现和基于路径的 review-trigger 默认加载。README、示例、技能规格和 CLI 文档改为只描述 `harness.yaml`。

## 验收标准

1. 全新临时仓库执行 `entrix init` 后只新增 `.mcp.json` 和 `harness.yaml`，其中不含 `docs/fitness/`。
2. 从生成的 `harness.yaml` 可运行 Fitness、review trigger、Harness 和 Stop Gate，且不依赖旧文件路径。
3. 已存在 `harness.yaml` 的 `entrix init` 不改写内容；`--force` 明确重建。
4. 旧 `docs/fitness/` 不再被任何命令读取；没有 `harness.yaml` 的 `stop-gate` 仅按未配置项目放行。
5. 默认模板维持当前质量策略的命令、硬门禁和 advisory 指标语义。
6. `entrix --help` 与 `entrix init` 成功输出均清楚列出子命令及其用途；命令帮助测试锁定关键文字和示例。

# Harness DoD 强门禁设计（2026-08-17）

当前强化阶段采用渐进增强现有 Harness 的方案，覆盖 fail-closed、Gate 级条件、标准报告解析、artifact 接线、PASS 强制重验和工作区指纹修复。完整设计与验收标准见：

- [`superpowers/specs/2026-08-17-harness-dod-hardening-design.md`](superpowers/specs/2026-08-17-harness-dod-hardening-design.md)
