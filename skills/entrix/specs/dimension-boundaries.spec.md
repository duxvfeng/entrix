# 维度边界规范

本文件回答一个主要设计问题：每个维度是否都应该有独立规范？

## 简短回答

通常，稳定维度应该有自己的规范指导。但维度并不是唯一重要的边界。

使用三层结构：

- Skill 入口负责工作流
- 基础规范负责共享规则
- 维度规范负责稳定的质量面

## 重要区分

- `dimension` 是 Entrix 使用的执行和报告概念
- `dimension` 是 `harness.yaml` 中 `fitness.dimensions` 下的一个唯一命名项
- `skill spec` 是面向代理的参考资料

这三层通常相互对应，但不必完全相同。

## 何时为一个维度设置独立规范

当某个质量面具有以下特征时，为它创建独立的维度规范：

- 独立的目标
- 独立的 metric 模式
- 独立的负责人或审查者
- 独立的失败含义
- 在 CI 或评分体系中的稳定位置

Routa.js 中的示例：

- `code_quality`
- `engineering_governance`
- `testability`
- `security`
- `api_contract`
- `release_readiness`
- `design_system`
- `ui_consistency`

## 何时合并或归组

当较小或关系紧密的质量面共享大部分编写规则时，将它们归入同一个规范。

示例：

- `observability` 和 `performance` 都是权重为 `0` 的运行时证据面，因此一个
  `dimension-runtime.spec.md` 就足以提供 Skill 指导。

## 一个维度包含多个 Metric 时

一个维度可以在 `metrics` 列表中保留多个可执行检查。使用 `tier`、
`execution_scope` 和 `run_when_changed` 等 metric 元数据表达生命周期差异，
而不必将配置拆到多个文件中。

## 决策规则

按顺序询问以下问题：

1. 这是新的关注点，还是已有关注点中的新 metric？
2. 该关注点是否已经有稳定的维度名称？
3. 该关注点是否需要为不同检查设置独立 metric，例如 shell 覆盖率和 E2E 矩阵？
4. 是否存在真实的构建或打包信号，应归入 `release_readiness` 而不是忽略？
5. 合并是否会增加更多困惑，而减少的文件数量并不足以抵消这种困惑？

## 编写建议

对于大多数仓库：

- 一个 Schema 基础规范
- 一个拆分与合并规则基础规范
- 每个稳定维度族一个 Skill 规范
- 一个或多个示例

这样可以在不重新制造庞大单体规范的情况下，为代理提供足够的结构。
