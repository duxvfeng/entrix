# README 与项目开发用法文档计划

> **面向 AI 代理的工作者：** 文档任务在当前 `main` 工作区内执行。步骤使用复选框（`- [ ]`）跟踪。

**目标：** 生成与当前实现一致的 README，并说明不同语言项目，尤其是 Java 项目的日常接入方式。

**架构：** README 作为入口文档，按“安装 → 初始化 → 开发 → 门禁 → CI/发布”组织；本地插件调试细节继续由 `docs/local-plugin-install.md` 承担。

**技术栈：** Markdown、Entrix CLI、`harness.yaml`、Claude Code MCP/Stop Hook、GitHub Actions。

---

### 任务 1：重写根 README

**文件：**

- 修改：`README.md`

- [ ] **步骤 1：** 写入当前插件、CLI、Harness、MCP 和 Stop Gate 的统一入口说明。
- [ ] **步骤 2：** 加入 Java Maven/Gradle profile、内存并发、CI scope 和开发日常流程。
- [ ] **步骤 3：** 加入 Release 二进制、缓存、故障排查和开发者验证命令。

### 任务 2：验证文档与实现一致

**文件：**

- 检查：`README.md`、`entrix/cli.py`、`entrix/harness/template.py`、`.claude-plugin/plugin.json`、`hooks/hooks.json`

- [ ] **步骤 1：** 运行 CLI help、workflow YAML 解析和旧路径扫描。
- [ ] **步骤 2：** 运行 Markdown 链接/代码块基础检查、`git diff --check`。
- [ ] **步骤 3：** 运行与文档相关的回归测试。
