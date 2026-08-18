# Fitness Skill 规范

像使用 `slide-skill/artifact_tool/README.md` 一样使用此索引：它是第二层级的导航图，
不是完整实现。

## 基础规范

- `harness-schema.spec.md`：`harness.yaml` 的必需和可选字段，以及何时使用高级
  metric 元数据。
- `dimension-boundaries.spec.md`：如何判断一个 metric 属于已有维度还是新的质量面。

## 维度规范

- `dimension-code-quality.spec.md`
- `dimension-engineering-governance.spec.md`
- `dimension-testability.spec.md`
- `dimension-security.spec.md`
- `dimension-api-contract.spec.md`
- `dimension-release-readiness.spec.md`
- `dimension-design-system.spec.md`
- `dimension-ui-consistency.spec.md`
- `dimension-runtime.spec.md`

## 示例

- `../examples/minimal-dimension.md`
- `../examples/advisory-probe-metric.md`
- `../examples/runtime-zero-weight-dimension.md`
- `../examples/entry-doc-topology.md`
- `../examples/ci-scoped-authoritative-metric.md`
- `../examples/toolchain-boundary-ci-scope.md`

## 阅读指导

只阅读当前任务所需的规范：

- 新增或编辑 metric：`harness-schema.spec.md` + 一个维度规范
- 新增或合并维度：`dimension-boundaries.spec.md`
- 判断是否新增维度：`dimension-boundaries.spec.md`
- 添加运行时证据：`dimension-runtime.spec.md`
- 决定如何处理构建或打包信号：`dimension-release-readiness.spec.md`
- 解决代理入口歧义：`../examples/entry-doc-topology.md`
- 建模仅 CI 权威检查：`../examples/ci-scoped-authoritative-metric.md`
- 建模本地工具链边界：`../examples/toolchain-boundary-ci-scope.md`
