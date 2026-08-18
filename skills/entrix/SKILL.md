---
name: entrix
description: 通过发现真实的质量信号、生成或更新 harness.yaml，并验证生成的护栏可执行，为仓库建立或修复单文件 Entrix 质量 Harness。
license: MIT
---

# Entrix Skill（技能说明）

命令提示：`/entrix [init] [phase planning|implementation] [harness validate|run]
[run] [stop-gate] [--repo <path>] [--profile <name>]`

确保目标仓库最终只有一个可用的 `harness.yaml`。它是 Fitness 维度、审查触发器、
证据生产者和门禁策略的唯一事实来源。不要创建或读取独立的 Fitness 目录、
manifest 或 review-trigger 文件。

Entrix 使用演化架构语境中的 “fitness”：一种可执行检查，用于衡量代码库是否仍然
满足某个质量或架构目标。面向用户的称呼是“质量护栏”。

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
