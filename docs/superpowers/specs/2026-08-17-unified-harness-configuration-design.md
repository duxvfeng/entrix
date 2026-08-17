# Entrix 单文件 Harness 配置设计

## 目标

将 Entrix 的 Fitness 规格、review trigger 规则和 Stop Gate 策略统一至项目根目录的 `harness.yaml`。`entrix init` 生成这一份配置；项目不再创建或读取 `docs/fitness/`、manifest 或单独的 review trigger 文件。

## 非目标

- 不兼容旧的 `docs/fitness/` 格式，也不提供自动迁移命令。
- 不新增远程 evidence、插件注册表或多配置文件继承。
- 不改变 Harness 的 evidence、gate DSL 和 hook 输出协议。

## 方案选择

采用原生内联 schema：`fitness.dimensions` 保存 Fitness 领域数据，`review_triggers.rules` 保存审查规则，`evidence_producers` 和 `gate_policies` 保持 Harness 的执行与裁决职责。

相对于把全部检查扁平化为 command producer，此方案保留 Fitness 的权重、分数、tier、scope、稳定性与变更触发语义；相对于把 Markdown 内容塞入 YAML 字符串，此方案只有一套结构化解析模型。

## 配置示意

```yaml
version: "harness/v1"

fitness:
  dimensions:
    - dimension: code_quality
      weight: 35
      tier: normal
      threshold: { pass: 100, warn: 90 }
      metrics:
        - name: ruff_pass
          command: ruff check .
          hard_gate: true
          tier: fast

review_triggers:
  rules:
    - name: security-sensitive-change
      paths: ["entrix/security/**"]
      action: require_human_review

evidence_producers:
  - id: fitness
    type: fitness
    name: Entrix Fitness
    builtin: entrix-fitness
  - id: review-trigger
    type: review
    name: Review Trigger
    builtin: entrix-review-trigger

gate_policies:
  - name: Fitness 必须通过
    severity: hard
    rule: { evidence_id: fitness, condition: 'status == "pass"' }
```

`fitness.dimensions` 中的每项字段与现有 `Dimension`/`Metric` 模型一一映射。`review_triggers.rules` 使用现有 `ReviewTriggerRule` 所需字段，不接受外部配置路径。

## 组件边界

`entrix.harness.config` 解析并验证完整 YAML，产出 `HarnessConfig`、`list[Dimension]` 和 `list[ReviewTriggerRule]`。它是 YAML 到领域对象的唯一边界。

`entrix.engine.run_fitness_report` 接受已经解析的 dimensions，不再调用 Markdown loader。`entrix.review_trigger` 提供从内联 mapping 构建规则的纯函数；评估函数继续接收领域规则。

`EvidenceEngine` 把全局 Fitness/Review 领域对象注入对应 builtin producer。Producer 只运行和序列化 evidence，不解析项目配置。

`entrix init` 在 `.mcp.json` 之外写入默认模板。若目标 `harness.yaml` 已存在则失败，除非用户指定 `--force`。所有质量命令以 `harness.yaml` 为输入；未配置项目不读取旧路径。

## 命令提示

`entrix --help` 提供中文任务导览，列出 `init`、`run`、`harness validate`、`harness run`、`review-trigger`、`stop-gate` 和 `serve` 的用途与最短示例。该导览补充 argparse 的参数帮助，不引入额外的 `guide` 或 `help` 子命令。

成功执行 `entrix init` 后，CLI 输出下一步命令清单：

```text
entrix harness validate harness.yaml  # 检查配置结构
entrix run                            # 执行 Fitness 指标
entrix harness run --json             # 收集 evidence 并输出门禁裁决
entrix stop-gate                      # 供 Claude Code Stop Hook 调用
```

这些提示只解释用途，不自动运行命令；输出不能包含对项目 Python 环境、绝对路径或终端颜色的假设。

## 默认模板

模板复用当前项目的策略：`ruff check .`、debug print 检查、`pytest`、CLI help、包构建、observability 和 performance advisory 指标；同时内联当前 review trigger 和 Fitness/Review Gate。模板使用项目现有策略的同一命令与阈值，保证初始化后的行为可预测。

## 错误处理

- 缺少 `harness.yaml`：`stop-gate` 放行；显式质量命令返回配置缺失错误。
- `fitness` 或 `review_triggers` 结构非法：`harness validate` 和相关命令失败，Stop Hook 阻断并返回配置错误。
- `entrix init` 遇到已有 `harness.yaml`：不写入、不改写，提示使用 `--force`。
- builtin producer 遇到执行错误：保留标准 evidence error，由硬 gate 阻断。

## 测试策略

- `entrix init` 首次创建、已存在保护、`--force` 重建与模板结构测试。
- 根帮助的任务导览，以及初始化成功输出的命令清单与说明测试。
- Harness loader 的 inline Fitness/review 映射、非法字段与无旧目录依赖测试。
- Fitness/report 和 review-trigger 从单文件配置运行的端到端测试。
- Stop Hook 在有配置、无配置、配置非法时的路由测试。
- 删除旧 loader 后执行完整 pytest、Ruff、Mypy 和 build。
