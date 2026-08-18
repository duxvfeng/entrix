# Harness 语言 Profile 设计

## 目标

让 `entrix init` 根据仓库标记自动选择语言模板，同时允许用户通过 `--profile` 显式选择模板。初始化仍然只写入 `.mcp.json`、`harness.yaml` 和一次性阶段标记，不执行任何检查。

## 方案

新增 `entrix.harness.profiles` 作为唯一的 profile 注册表和识别入口。`auto` 按根目录 manifest 标记识别单一项目类型；没有匹配时回退到 `generic`；匹配多个项目类型时返回明确错误，要求显式 `--profile`，避免为多语言仓库生成错误命令。显式 profile 不依赖自动识别，可用于多模块或混合仓库。

支持的 profile：`generic`、`python`、`node-typescript`、`java-maven`、`java-gradle`、`go`、`rust`，以及默认模式 `auto`。

模板继续输出现有 `harness/v1` 单文件结构。每个语言模板提供该生态常用的 lint、test、build Fitness 指标，并在 Java 模板中固定 Maven `-T1`、Surefire `forkCount=1`/`reuseForks=true` 或 Gradle `--max-workers=1`。语言模板增加 `when.files_exist` 标记和 docs 分支排除条件；Gate Engine 仍只接收标准 Evidence，不识别具体工具。

## 错误与兼容性

- `entrix init --profile auto` 是无参数时的默认行为。
- 已存在 `harness.yaml` 时仍需 `--force` 才覆盖。
- 自动识别冲突在写文件前失败，并提示可用的显式 profile。
- `render_default_harness()` 和 `default_harness_config()` 保留无参数调用，继续代表 generic 模板，兼容现有 API 与测试。

## 验收

- parser 接受 `--profile` 并默认值为 `auto`。
- 空目录回退 generic；单一 marker 识别对应 profile；多 marker 要求显式 profile。
- `--dry-run` 输出选中的 profile 和对应语言命令，且不写文件、不执行检查。
- 生成的各 profile YAML 均可被 `load_harness_config()` 校验。
