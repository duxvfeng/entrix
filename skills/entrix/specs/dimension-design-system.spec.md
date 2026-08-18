# 设计系统（Design System）维度规范

编辑 `harness.yaml` 中的 `design_system` 维度时使用本规范。

## 目的

保护组件系统的一致性、设计 token、无障碍层，以及超出单个页面外壳范围的视觉契约。

## 典型信号

- token 或 CSS 契约检查
- 组件层视觉回归
- 面向无障碍的检查
- design-system 覆盖率矩阵

## 边界

让此维度专注于可复用的系统质量。

如果仓库将页面外壳或导航外壳视为独立质量面，则将相关关注点移到
`ui_consistency`。
