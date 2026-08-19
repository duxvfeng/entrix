# Harness 语言 Profile 实现计划

> **面向 AI 代理的工作者：** 本计划已获批准，直接在当前 `main` 工作区执行。步骤使用复选框跟踪进度。

**目标：** 为 `entrix init` 增加自动项目语言识别和显式 profile 模板选择。

**架构：** `profiles.py` 维护 marker 注册和冲突策略；`template.py` 按 profile 生成现有 `harness/v1` 字典；`cmd_init()` 解析 profile、生成 YAML 并报告最终选择。自动识别只负责选择，不参与 Evidence 或 Gate 执行。

**技术栈：** Python 3.11+、`pathlib`、`dataclasses`、PyYAML、argparse、pytest。

---

### 任务 1：profile 注册与识别

**文件：** 创建 `entrix/harness/profiles.py`；创建 `tests/harness/test_profiles.py`。

- [x] 定义 `auto`、`generic`、Python、Node/TypeScript、Java Maven、Java Gradle、Go、Rust profile 及 marker。
- [x] 单一匹配返回对应 profile；空目录回退 generic；多个匹配抛出带显式命令提示的错误。
- [x] 为每种 marker 和冲突行为添加单元测试。

### 任务 2：语言模板

**文件：** 修改 `entrix/harness/template.py`；修改 `tests/harness/test_template.py`。

- [x] 保留现有 generic 模板 API。
- [x] 添加按 profile 生成配置的 API 和 Python、Node/TypeScript、Java、Go、Rust 命令。
- [x] Java/Gradle 模板声明单进程/单 worker 参数，并使用 `when.files_exist` 与 branch 条件。
- [x] 验证所有模板可加载为 `harness/v1`。

### 任务 3：接入 init CLI

**文件：** 修改 `entrix/cli.py`；修改 `tests/test_cli.py`。

- [x] 增加 `init --profile`，默认 `auto`，并在 dry-run/成功消息中报告最终 profile。
- [x] 冲突时不写文件；显式 profile 可绕过冲突。
- [x] 保持 init 不执行验证、Fitness、Harness 或 Stop Gate。

### 任务 4：Skill 与文档

**文件：** 修改 `skills/entrix/SKILL.md`；修改 `README.md`。

- [x] 说明自动识别、显式 profile、冲突处理和 Java 资源限制。
- [x] 保留初始化后询问用户再运行检查的流程。

### 任务 5：验证与提交

**文件：** 无新增文件。

- [x] 运行 profile、模板、CLI 针对性测试。
- [x] 运行全量 pytest、Ruff、Mypy、配置校验和 `git diff --check`。
- [x] 提交中文 Conventional Commit。
