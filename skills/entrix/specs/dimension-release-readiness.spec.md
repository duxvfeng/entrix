# 发布就绪（Release Readiness）维度规范

当仓库已经存在真实的 build、package、Docker 或 CLI 冒烟命令时，编辑
`release_readiness` 证据使用本规范。

## 目的

保护仓库是否仍能生成计划交付的制品。

## 典型信号

- `npm run build`
- package 或 bundle 命令
- Docker build 命令
- 二进制构建命令
- 验证可分发入口的 CLI 冒烟命令

## 何时创建

当仓库存在有意义的生产或交付构建信号，且该信号尚未被其他维度覆盖时，创建
`release-readiness`。

如果仓库拥有：

- `lint`
- `test`
- `build`

那么忽略 `build` 通常是错误的。应为它设置一个维度，或明确记录它为何不在范围内。

## 边界

让此维度专注于可交付性。

除非以下内容属于实际发布面，否则不要将其移到此维度：

- 通用代码质量检查
- 端点契约测试
- 浏览器 E2E 流程
- 运行时可观测性 probe

## 权重指导

对于最小仓库，`release_readiness` 通常是补齐最后权重差额、同时保持总和为 `100` 的
最简单位置，不会扭曲其他维度的含义。
