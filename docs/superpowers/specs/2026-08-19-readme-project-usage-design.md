# README 与项目开发用法文档设计

## 目标

重写根目录 `README.md`，使其与当前 Entrix 实现一致，并让首次接入者能在不阅读源码的情况下完成安装、初始化、日常开发检查和 CI 接入。

## 文档边界

- README 说明核心概念、最短安装路径、`harness.yaml`、MCP、Stop Gate、Java 项目用法、二进制插件和常见故障。
- `docs/local-plugin-install.md` 保留本地源码插件和离线调试的详细步骤。
- 文档必须明确 MCP `serve` 和 Stop Gate `stop-gate` 是两条独立链路。
- 文档必须明确 `entrix init` 只生成配置，不自动执行检查。
- 文档不得把 `docs/fitness`、硬编码规则或 Python/`uvx` 描述为正式二进制插件的必需依赖。

## 读者流程

1. 安装 Claude Code 插件或 Python CLI。
2. 在目标项目执行 `entrix init --profile auto`，必要时显式选择语言 profile。
3. 审查并调整根目录 `harness.yaml`。
4. 依次运行 `harness validate`、fast 检查和完整 Harness 仲裁。
5. 开发阶段通过 MCP 主动查询，任务结束时由 Stop Hook 被动裁决。
6. 在 CI 中执行同一份 YAML 配置，并将二进制插件通过 GitHub Release 发布。

## 验收标准

- README 中的命令与当前 CLI 帮助、profile 模板和插件清单一致。
- README 包含 Maven/Gradle 的单路并发和 JVM 总内存说明。
- README 包含 Stop Gate 的 stdin JSON 输入和 stdout 决策契约。
- README 包含 GitHub Actions 工件与 Release 附件的区别。
- README 不再引用已经废弃的 `docs/fitness` 作为运行时配置来源。
