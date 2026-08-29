# 文档索引

Entrix 文档导航。历史设计与实施记录已归档至 [archive/](archive/)；更早的
实施计划位于 [superpowers/plans/](superpowers/plans/)，不能作为当前功能状态依据。

## 使用与集成

- [command-reference.md](command-reference.md) — CLI 命令速查
- [stop-gate-usage.md](stop-gate-usage.md) — Stop Gate 使用说明
- [mcp-vs-stop-gate.md](mcp-vs-stop-gate.md) — MCP 与 Stop Gate 两条通道的职责划分
- [plugin-installation-guide.md](plugin-installation-guide.md) — Claude Code 插件安装
- [local-plugin-install.md](local-plugin-install.md) — 本地插件调试安装
- [claude-integration-flow.md](claude-integration-flow.md) — Claude 集成链路全貌
- [lifecycle.svg](lifecycle.svg) — 生命周期图

## 开发与发布

- [github-actions-guide.md](github-actions-guide.md) — CI 工作流说明
- [release-checklist.md](release-checklist.md) — 双远端（GitHub + Gitee）发布顺序清单
- [execution-flow.md](execution-flow.md) — 入口到子命令的执行路径
- [lint-config-guide.md](lint-config-guide.md) — 可配置 Lint 系统使用指南
- [lint-config.md](lint-config.md) — 本仓库自身 harness.yaml 的 lint 配置现状（dogfooding）
- [../CHANGELOG.md](../CHANGELOG.md) — 版本变更日志

## 设计

- [design.md](design.md) — harness / Stop Gate 修复设计
- [adr/](adr/) — 架构决策记录
- [diagrams/](diagrams/) — 图表素材

## 过程记录

- [plan.md](plan.md) — 当前路线图（唯一有效的计划入口）
- [notes/](notes/) — 修复与状态笔记
- [testing/](testing/) — TDD 过程记录
- [multi_agent_system/](multi_agent_system/) — 多智能体资料（不参与 lint/mypy）

## 归档

- [archive/](archive/) — 已过期或已被实现取代的历史文档（如 Stop Gate 实现前
  的设计风险记录、2026-08-14 的初始设计与实施计划），仅作历史参照。
