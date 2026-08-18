# 运行时（Runtime）维度规范

编辑 `harness.yaml` 中的 `observability` 或 `performance` 维度时使用本规范。

## 目的

保护有价值、但当前可能不参与加权评分的运行时证据。

## 常见结构

运行时维度通常使用：

- `weight: 0`
- advisory 或 probe 类型的 metric
- `execution_scope: ci`、`staging` 或 `prod_observation`
- `evidence_type: probe`
- 当信号不确定时使用 `stability: noisy`

## 为什么一个规范就够了

`observability` 和 `performance` 通常共享编写规则：

- 它们面向运行时
- 它们通常产生证据，而不是严格的 pass/fail 结论
- 它们经常需要高级 metric 元数据

因此，即使仓库保留两个独立的 evidence 文件，一个共享的 Skill 规范也足够。

## 边界

除非仓库已经拥有非常稳定的信号和明确的运维负责人，否则不要将运行时 probe 转成
硬门禁。
