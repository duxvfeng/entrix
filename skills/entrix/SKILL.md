---
name: entrix
description: 通过发现真实的质量信号、生成或更新 harness.yaml，并验证生成的护栏可执行，为仓库建立或修复单文件 Entrix 质量 Harness。
license: MIT
---

# Entrix Skill（技能说明）

## 对话语言

- 默认使用简体中文回答用户。
- 面向用户的解释、结论、错误说明和建议使用中文。
- 代码、命令、路径、标识符、JSON 字段名和原始工具输出保持原样。
- 用户明确要求英文时，再使用英文回答。

## 命令提示

**基础命令：**
```
/entrix init                    # 初始化配置文件
/entrix run                     # 运行质量检查  
/entrix harness validate         # 验证配置正确性
/entrix harness run             # 执行完整的 Harness 检查
```

**高级命令：**
```
/entrix phase planning          # 标记为规划阶段
/entrix phase implementation     # 标记为实现阶段
/entrix review-trigger          # 检查需要人工审查的变更
/entrix stop-gate              # 作为 Stop Hook 执行
```

**选项参数：**
```
--repo <path>                   # 指定仓库路径
--profile <name>               # 指定语言配置 (python|node-typescript|java-maven|java-gradle|go|rust)
--tier fast|normal|deep        # 执行层级
--json                         # 输出 JSON 格式
```

在 Marketplace 插件中，以上命令由插件目录里的 Node 启动器执行，不依赖用户的
`PATH` 或 Python 环境。需要实际执行时使用：

```bash
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" init --repo .
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" trust --repo .
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" run --repo .
node "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" phase implementation --repo .
```

Marketplace 模式下 `init` 只创建或更新 `harness.yaml`；MCP 和 Stop Hook 已由
`plugin.json` 注册，不要手工把第二个 Entrix server 写入 `.mcp.json`。独立 Python
安装再使用 `entrix ...` 命令。打开已有仓库或修改 Harness 后，先检查配置并运行
`trust`；未确认的配置不会在 Stop Hook 中自动执行命令。

## 可配置 Lint 系统

Entrix 现在支持通过 YAML 配置文件自定义 lint 工具，而不是硬编码：

**配置文件位置：**
- `.claude/lint-config.yaml` (项目级别，推荐)
- `skills/entrix/lint-config.yaml` (默认配置)

**支持的语言和工具：**
- 🐍 **Python**: ruff, mypy, black, flake8, pylint
- 📦 **Node/TypeScript**: eslint, typescript, vue lint, prettier  
- ☕ **Java Maven**: spotbugs, checkstyle, pmd
- 🏗️ **Java Gradle**: spotbugs, checkstyle, detekt
- 🔵 **Go**: gofmt, go vet, golangci-lint, staticcheck
- 🦀 **Rust**: cargo fmt, cargo clippy

**自定义配置示例：**
```yaml
# .claude/lint-config.yaml
languages:
  python:
    code_quality:
      - name: ruff_lint
        enabled: true
        required: true
      - name: mypy_check
        enabled: true
        required: false
```

确保目标仓库最终只有一个可用的 `harness.yaml`。它是 Fitness 维度、审查触发器、
证据生产者和门禁策略的唯一事实来源。不要创建或读取独立的 Fitness 目录、
manifest 或 review-trigger 文件。

Entrix 使用演化架构语境中的 “fitness”：一种可执行检查，用于衡量代码库是否仍然
满足某个质量或架构目标。面向用户的称呼是“质量护栏”。

## Marketplace 插件的 Stop Hook

Marketplace 安装时，Stop Hook 由插件 manifest 提供，并在目标仓库根目录执行。
插件 hook 必须调用 Node.js 启动器 `${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs`，并传入
`stop-gate` 参数；不要使用 `${CLAUDE_PLUGIN_ROOT}/bin/entrix`、`./hooks/stop-gate.sh`、
`python -m entrix` 或其他相对项目目录的路径。`${CLAUDE_PLUGIN_ROOT}` 指向已安装的插件目录，
而不是当前项目目录。启动器会按当前平台下载、校验并缓存对应的 Entrix 二进制。

`entrix init` 只在目标仓库创建 `.mcp.json`、`harness.yaml` 和阶段标记，不注册项目级
Stop Hook，也不加载项目中的 `hooks/stop-gate.sh`。使用 Marketplace 插件时，项目只需
初始化 `harness.yaml`，Stop Hook 继续使用插件目录中的启动器。

## Skill 目录内容

- `specs/README.md`：可用参考资料索引
- `specs/harness-schema.spec.md`：单文件配置 Schema
- `specs/dimension-boundaries.spec.md`：如何新增或合并维度
- `specs/dimension-*.spec.md`：各维度的指导说明
- `examples/`：可复制的 `harness.yaml` 片段
- `../../tests/fixtures/skill_regression/`：Skill 回归 Harness 使用的内置仓库 profile

## 阅读顺序

对于任何初始化或修复任务，都按以下顺序阅读：

1. 目标仓库中存在时的 `AGENTS.md` 和 `CLAUDE.md`
2. 目标仓库的 manifest 与任务运行器：`package.json`、`pyproject.toml`、
   `Cargo.toml`、`justfile`、`Makefile`
3. 目标仓库的 `.github/workflows/**`
4. 目标仓库已有的 `harness.yaml`（如果存在）
5. 本 Skill 的 `specs/README.md`
6. `specs/harness-schema.spec.md`，以及完成当前任务所需的维度规范
7. 当入口文档或 CI 边界行为不明确时，匹配的 `examples/*.md`

## 核心规则

- 只使用仓库中的真实信号，不要凭空编造命令。
- 在仓库根目录保留一个 `harness.yaml`，不要创建旁路质量配置文件。
- 优先使用对仓库根目录安全的包装器，例如 `just`、`make`、`npm run` 或
  `cargo --manifest-path ...`。
- 加权维度总和必须严格为 `100`；仅提供建议的维度使用 `weight: 0`。
- 保持默认本地 `entrix run` 为绿色。需要 CI 环境的权威检查使用
  `execution_scope: ci` 建模，不要把它作为本地 fast 硬门禁。
- 安装 Claude Stop Gate 后，它是完整 Harness 运行的唯一权威入口。不要让 Claude
  在停止前立即运行 `entrix run` 或 `entrix harness run`；这会重复昂贵检查，
  还可能与 JVM/Gradle 进程重叠。
- 将任务阶段视为 Stop Gate 生命周期的一部分。在规划或头脑风暴开始时运行
  `entrix phase planning --repo .`；只有用户明确批准实现后，才运行
  `entrix phase implementation --repo .`。
- 只有仓库存在真实命令或 CI 信号时，才添加安全或发布指标。
- 确保每个已有的代理入口文档都可被发现：如果存在 `AGENTS.md` 和 `CLAUDE.md`，
  让它们指向 `harness.yaml`；如果两者都不存在，只创建最小的 `AGENTS.md`。

## Harness Schema（配置结构）

使用标准的单文件结构：

```yaml
version: "harness/v1"
fitness:
  dimensions:
    - dimension: code_quality
      weight: 50
      threshold: {pass: 100, warn: 90}
      metrics:
        - name: lint
          command: npm run lint 2>&1
          hard_gate: true
          tier: fast
          description: Lint must pass.
    - dimension: testability
      weight: 50
      threshold: {pass: 100, warn: 90}
      metrics:
        - name: unit_tests
          command: npm run test:run 2>&1
          hard_gate: true
          tier: normal
          execution_scope: ci
          description: The authoritative suite runs in CI.
review_triggers:
  rules:
    - name: risky_core_change
      type: changed_paths
      paths: [src/core/**]
      severity: high
      action: require_human_review
evidence_producers:
  - id: fitness
    type: fitness
    name: Entrix Fitness
    builtin: entrix-fitness
gate_policies:
  - name: Fitness must pass
    severity: hard
    rule:
      evidence_id: fitness
      condition: status == "pass"
```

维度标识符使用 `snake_case`。一个维度包含完整的 `metrics` 列表，名称必须唯一。
常用 metric 字段包括 `name`、`command`、`pattern`、`hard_gate`、`tier` 和
`description`。只有仓库确实需要时，才使用 `execution_scope`、
`timeout_seconds`、`gate`、`evidence_type`、`confidence`、`stability`、`kind`、
`analysis`、`owner`、`run_when_changed` 和 `waiver` 等高级字段。

## 工作流

### 1. 检查仓库

如果当前调用仍处于规划或头脑风暴阶段，在读取或修改配置前先标记阶段：

```bash
entrix phase planning --repo .
```

从 package scripts、任务运行器、CI 工作流、已提交的辅助脚本和已有
`harness.yaml` 中识别真实信号。优先使用仓库本地命令，其次使用从 CI 中提取的
根目录安全命令，只有在工作目录明确时才直接调用工具。

### 2. 设计维度

使用稳定的关注点名称，例如 `code_quality`、`testability`、`security`、
`release_readiness`、`api_contract`、`design_system`、`ui_consistency`、
`observability` 和 `performance`。将相关检查作为同一维度中的 metric；只有确实
独立的质量面才创建新维度。

### 3. 创建或修复 `harness.yaml`

对于新仓库，优先使用 `entrix init --repo .`。`init` 默认使用
`--profile auto`，根据仓库标记选择语言模板：

- `pyproject.toml`、`pytest.ini`、`requirements.txt`、`setup.py` 或 `setup.cfg` -> `python`
- `package.json` 或 `tsconfig.json` -> `node-typescript`
- `pom.xml` -> `java-maven`
- `build.gradle`、`build.gradle.kts` 或 Gradle wrapper -> `java-gradle`
- `go.mod` -> `go`
- `Cargo.toml` -> `rust`

空仓库或无法识别的仓库使用 `generic`。如果检测到多个 profile，应停止并要求用户
显式选择，例如 `entrix init --repo . --profile java-maven`。支持的显式 profile 包括
`generic`、`python`、`node-typescript`、`java-maven`、`java-gradle`、`go` 和
`rust`。将生成的 Fitness、review-trigger、producer 和 policy 部分集中在同一个
文件中；只有检查确认仓库使用了不同的真实任务运行器时，才调整命令。

Java 模板会有意限制进程扩散：Maven 使用 `-T1`，测试使用
`-DforkCount=1 -DreuseForks=true`；Gradle 使用
`--no-daemon --max-workers=1`。这些参数会限制构建工具自身的 worker，此外还受
Entrix 外层 producer 上限控制。

如果入口文档已经存在，添加一条简短说明，指出规则位于 `harness.yaml`。不要把完整
配置复制到入口文档中。

#### 初始化必须保留 Lint 质量护栏

初始化完成后，检查生成的 `harness.yaml` 中的 `fitness.dimensions`：

- 如果仓库存在真实的 lint、格式化或静态分析命令，`code_quality` 必须至少包含一个
  对应的 metric，并保留其真实命令、`tier` 和门禁语义。优先使用仓库 manifest、任务运行器、
  CI 或已有配置中的命令，例如 `ruff check .`、`npm run lint`、`gofmt -l .`、
  `cargo clippy`、Checkstyle 或 SpotBugs。
- 如果生成模板没有包含已发现的 lint 命令，在初始化回合内补入 `harness.yaml`，不要只在
  skill 或入口文档中描述它。
- 如果仓库没有任何真实 lint 信号，不要凭空添加工具；可以保留格式检查、编译检查或其他
  已确认的 `code_quality` 信号，并在结果中说明没有可初始化的 lint 命令。
- lint 检查默认应放在 `fast` tier；只有仓库真实命令需要更重的资源时才使用其他 tier 或
  `execution_scope: ci`。不要把不存在的可选工具放进默认本地门禁。

### 4. 校验前先询问

`entrix init` 会创建 `.mcp.json`、`harness.yaml` 和一次性运行时阶段标记。创建或
修复配置后，报告变更的文件并询问用户：

```text
Configuration is ready. Do you want to run configuration validation or local checks now?
```

在用户明确回答“是”之前，不要运行 `entrix harness validate`、`entrix run --dry-run`、
`entrix run --tier fast`、`entrix harness run` 或 Stop Gate。初始化、创建或修复配置的
请求，不等于允许执行检查。

当用户批准实现工作后，在编辑源码或运行实现检查前切换阶段：

```bash
entrix phase implementation --repo .
```

`entrix init` 会自动写入一次性初始化阶段。Stop Hook 会在本次初始化回合结束时消费
该标记，因此在用户回答确认问题前，创建配置不会触发完整 Harness 运行。

获得明确校验许可后，按以下顺序选择可用的 Entrix 调用方式：`entrix`、
`uvx --from entrix entrix`，最后是 `python3 -m entrix`。

```bash
entrix harness validate harness.yaml
entrix run --dry-run
entrix run --tier fast
```

在停止前修复无效 Schema、重复名称、权重、路径和非本地命令。如果某个命令仅适用于
CI，将它移到 `execution_scope: ci`，并在默认路径中保留廉价的本地冒烟检查。

对于用户明确要求的完整诊断运行，在请求 Stop 前等待它结束。JVM/Gradle metric 必须
设置 `timeout_seconds`，并使用 `--no-daemon --max-workers=1`，除非仓库已批准更高
worker 数的资源预算。

## 质量标准

只有满足以下条件，Skill 才算完成：

- `harness.yaml` 存在；用户明确要求校验时，配置能够通过校验
- 正权重 Fitness 维度总和为 `100`
- 每个 metric 都对应仓库中的真实信号
- review-trigger、producer 和 gate policy 都内联在配置中
- 已有代理入口文档指向 `harness.yaml`
- 用户要求运行本地 `entrix run` 时，它为绿色，或报告明确的仓库阻塞项
- `entrix run --dry-run` 和可用的 fast-tier 检查只在用户明确批准后运行

## 避免事项

- 为一个仓库创建多个配置文件
- 编造命令或安全工具
- 将由 CI 提供环境的测试套件作为默认本地 fast 硬门禁
- 将无法运行的可选工具放入默认本地执行路径
- 仅因 `entrix init` 成功就运行校验或检查
- 只生成看起来合理的配置就停止
