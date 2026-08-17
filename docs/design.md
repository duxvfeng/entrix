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
