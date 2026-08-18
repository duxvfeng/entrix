# Harness Schema 规范

Entrix 读取仓库根目录的一个 `harness.yaml`。该文件包含所有可执行的 Fitness、
review、evidence 和 gate policy 数据。

## 必需结构

```yaml
version: "harness/v1"
fitness:
  dimensions:
    - dimension: code_quality
      weight: 100
      threshold: {pass: 100, warn: 90}
      metrics:
        - name: lint
          command: npm run lint 2>&1
          hard_gate: true
          tier: fast
review_triggers: {rules: []}
evidence_producers: []
gate_policies: []
```

## 维度规则

- `fitness.dimensions` 是名称唯一的维度列表。
- 每个维度包含 `dimension`、非负 `weight`、`threshold` 和 `metrics` 列表。
- 生效的加权维度总和必须严格为 `100`。
- 同一维度内的 metric 名称必须唯一。每个 metric 都需要非空的 `name` 和 `command`。
- 维度和 metric 名称使用 `snake_case`。

## Metric 字段

从 `name`、`command`、`pattern`、`hard_gate`、`tier` 和 `description` 开始。只有
仓库有特定需要时，才添加 `execution_scope`、`timeout_seconds`、`gate`、
`evidence_type`、`confidence`、`stability`、`kind`、`analysis`、`owner`、
`run_when_changed` 或 `waiver`。

命令从仓库根目录运行。优先使用仓库已有的包装器，并将仅 CI 权威检查放在
`execution_scope: ci` 后面。

## Review、Producer 和 Gate

- 将 review 规则放入 `review_triggers.rules`。
- 在 `evidence_producers` 中定义 command 或 builtin producer。
- 每个 `gate_policies[].rule` 引用一个 evidence id 或 type。
- Entrix 的 builtin producer 使用 `entrix-fitness`、`entrix-review-trigger` 和
  `diff-stats`。

## 反模式

- 重复的维度或 metric 名称
- 总和不为 `100` 的权重
- `echo TODO` 一类的占位命令
- 依赖未安装工具的本地硬门禁
- 为维度、manifest 或 review 规则创建独立文件
