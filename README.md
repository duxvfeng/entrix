<h1 align="center">Entrix</h1>

<p align="center">
  <strong>将质量保障从人工审查转变为可执行的变更门禁。</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/entrix/">
    <img src="https://img.shields.io/pypi/v/entrix.svg" alt="PyPI version" />
  </a>
  <a href="https://pypi.org/project/entrix/">
    <img src="https://img.shields.io/pypi/pyversions/entrix.svg" alt="Python versions" />
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License" />
  </a>
</p>

<p align="center">
  <img src="https://gitee.com/duxvfeng/entrix/raw/main/docs/lifecycle.svg" alt="Entrix 生命周期" width="85%" />
</p>

<br>

Entrix 是一个面向 AI 辅助开发流程的质量门禁工具。它把测试、Lint、构建、架构约束、变更风险和代码影响分析统一为可配置、可审计的质量信号，并通过 CLI、MCP 和 Claude Code Stop Hook 提供三种使用方式。

三条入口链路的职责不同：

| 入口 | 触发时机 | 主要用途 | 输出 |
| --- | --- | --- | --- |
| `entrix run` | 开发者主动执行 | 直接运行 Fitness 指标 | 终端报告或 JSON |
| `entrix serve` | Claude 在对话中主动调用 | MCP 工具查询质量和影响范围 | MCP 工具结果 |
| `entrix stop-gate` | Claude Code 准备结束任务时 | 任务结束前执行独立门禁 | 空 stdout 放行，JSON 阻断 |

MCP 和 Stop Gate 是两条独立通道：MCP 负责开发过程中的主动反馈，Stop Gate 负责任务结束时的被动裁决。Stop Gate 不依赖 Claude 是否主动调用过 MCP。

一次 Harness 运行的主链路如下：

```text
harness.yaml
    |
    v
配置加载与校验
    |
    +--> Fitness Dimensions ------> entrix run / entrix-fitness producer
    |
    +--> Evidence Producers ------> Evidence Bundle
    |                                  |
    +--> Gate Policies --------------> Gate Engine
                                       |
                                       v
                              PASS / FAIL / BLOCKED
```

## 快速开始

选择一种安装方式：

### Claude Code 插件（推荐）

```bash
/plugin marketplace add https://gitee.com/duxvfeng/entrix.git
/plugin install entrix@entrix
```

安装后请重启 Claude Code。

当前正式插件版本为 [`v0.1.24`](https://github.com/duxvfeng/entrix/releases/tag/v0.1.24)。
插件会固定使用与该版本匹配的二进制，不会把最新源码和旧版本二进制混用。

#### 默认对话语言

从 `v0.1.24` 开始，Entrix Skill 默认要求 Claude：

- 使用简体中文回答用户；
- 使用中文提供解释、结论、错误说明和建议；
- 保留代码、命令、路径、标识符、JSON 字段名和原始工具输出；
- 用户明确要求英文时再使用英文回答。

这项约定控制 Claude 的自然语言回复，不会翻译 MCP/Stop Gate 协议字段或底层二进制的原始 stdout/stderr。
已经安装旧版本的电脑需要更新或重新安装 `entrix` 插件；旧插件缓存不会自动包含新的 Skill 规则。

插件内置无 Python 启动器。首次调用 MCP 或 Stop Gate 时，Node.js 启动器会按当前平台从 GitHub Release 下载固定版本的单文件 Entrix 二进制，验证签名 manifest、签名 checksum 和 SHA-256 后缓存；后续调用直接使用缓存。因此安装插件和运行门禁**不要求本机安装 Python、pip、uv 或 uvx**，但 Claude Code 所在环境需要有 Node.js。

支持的平台资产：

```text
entrix-<version>-windows-amd64.exe
entrix-<version>-linux-amd64
entrix-<version>-linux-arm64
entrix-<version>-macos-amd64
entrix-<version>-macos-arm64
```

缓存目录：
- Unix：`~/.cache/entrix/bin/<version>/<target>/`
- Windows：`%LOCALAPPDATA%\entrix\bin\<version>\<target>\`

开发者可用环境变量：
- `ENTRIX_BINARY_PATH`：指定本地可执行文件路径
- `ENTRIX_RELEASE_REPOSITORY`：测试镜像仓库（格式 `owner/repo`）
- `ENTRIX_RELEASE_BASE_URL`：自定义 Release 下载地址
- `ENTRIX_DOWNLOAD_TIMEOUT_SECONDS`：每个下载请求的超时时间，默认 `120`
- `ENTRIX_STATE_DIR`：Stop Gate 状态、信任记录和 verdict 缓存目录
- `ENTRIX_STOP_GATE_DISABLED=1`：显式绕过 Stop Gate（仅用于开发/故障排查，生产环境不应设置）

插件启动器还会读取插件内置的 `security/release-public-key.pem`。签名、manifest 或 checksum 任一校验失败都会拒绝执行并删除临时下载，不要通过替换公钥或关闭校验来绕过错误。

### 独立 CLI（`uv` 或 `pip`）

```bash
# 使用 uv（推荐）
uv tool install entrix

# 或使用 pip
pip install entrix

# 验证安装
entrix --help
```

需要 Python 3.11+。

如需集成 Claude Code MCP：

```bash
entrix install --repo .
```

<details>
<summary><strong>它能做什么</strong></summary>

- 将质量门禁和架构约束编码为可复用的护栏规格
- 按 `fast` / `normal` / `deep` 层级运行检查
- 基于 diff 运行变更感知检查，支持加权评分和硬门禁
- 通过 `review-trigger` 将高风险变更路由到更深入的验证
- 可选添加基于图的影响分析、测试半径和审查上下文分析

</details>

<details>
<summary><strong>变更生命周期中的护栏</strong></summary>

- 在风险代码落地前运行检查
- 每次运行都会生成证据
- 策略可以自动硬阻断、警告或升级至人工审查

</details>

## 核心概念

### Harness 配置

Entrix 使用单一的 `harness.yaml`（或 `.harness/harness.yaml`）作为质量规则配置源：

- **Evidence Producers**：定义证据收集器（测试、lint、构建等）
- **Gate Policies**：定义门禁策略，基于证据裁决 PASS/FAIL
- **Fitness Dimensions**：基于维度的加权质量护栏
- **Review Triggers**：高风险变更升级规则

### MCP vs Stop Gate

Entrix 提供两条独立的集成路径：

1. **MCP（`entrix serve`）**：主动工具调用通道
   - Claude 在开发过程中主动查询代码质量
   - 提供实时的架构约束和质量反馈

2. **Stop Gate（`entrix stop-gate`）**：被动门禁通道
   - 在 Claude 请求结束任务时自动触发
   - 独立收集证据，按策略裁决是否允许结束
   - 失败时返回可执行的修复反馈

## 首次使用

### 1. 初始化配置

在项目根目录运行：

```bash
entrix init --repo .
```

支持的 profile：
- `auto`：自动检测项目类型（默认）
- `generic`：通用项目
- `python`、`node-typescript`、`java-maven`、`java-gradle`、`go`、`rust`

Profile 的检测标记和默认命令如下。Profile 只提供可审查的初始模板，生成后应按项目实际情况调整 `harness.yaml`。

| Profile | 检测标记 | 默认检查 |
| --- | --- | --- |
| `python` | `pyproject.toml`、`pytest.ini`、`requirements.txt`、`setup.py`、`setup.cfg` | `ruff check .`、`python -m pytest`、`python -m build --no-isolation` |
| `node-typescript` | `package.json`、`tsconfig.json` | `npm run lint/test/build --if-present` |
| `java-maven` | `pom.xml` | `mvn -B -T1` 的 validate、test、package |
| `java-gradle` | `build.gradle`、`build.gradle.kts`、`gradlew`、`gradlew.bat` | `gradlew --no-daemon --max-workers=1` 的 check、test、assemble |
| `go` | `go.mod` | `go vet ./...`、`go test ./...`、`go build ./...` |
| `rust` | `Cargo.toml` | `cargo fmt`、`cargo test --workspace`、`cargo build --workspace` |

如果 `auto` 同时检测到多个项目类型，命令会要求显式指定 `--profile`；没有匹配标记时使用 `generic`。

对于特定项目类型：

```bash
entrix init --repo . --profile java-maven
entrix init --repo . --profile node-typescript
```

**重要**：`entrix init` 只生成配置文件，**不执行任何检查**。配置完成后需要手动确认并运行检查命令。

### 2. 审查配置

检查生成的 `harness.yaml`：

```bash
entrix harness validate harness.yaml
```

`harness.yaml` 中的 `command` 会执行项目命令。交给 Stop Hook 或 MCP 前，应先审查命令、路径、环境条件和超时设置。`entrix init` 会自动信任刚生成的配置；手工创建或替换配置后，需要显式信任：

```bash
entrix trust --repo .
```

未信任的 Harness 不会被 MCP 自动执行。配置发生实质变化后，需要重新审查并重新信任。

### 3. 运行检查

确认配置后，按需运行检查：

```bash
# 快速检查（冒烟测试）
entrix run --tier fast

# 完整检查
entrix run --tier normal

# 仅检查特定维度
entrix run --tier normal --dimension code_quality --dimension testability

# 基于变更的增量检查
entrix run --changed-only --base HEAD~1
```

### 4. 开发流程

**主动开发阶段（MCP）**：

```bash
# 启动 MCP server
entrix serve
```

Claude 可在开发过程中主动调用质量检查工具。

**任务结束阶段（Stop Gate）**：

Stop Gate 通过 Claude Code hooks 自动触发，无需手动调用。配置完成后自动生效：

1. Claude 完成修改并尝试结束任务
2. Claude Code 调用 `entrix stop-gate`
3. Entrix 独立收集证据并裁决
4. **PASS**：允许结束
5. **FAIL**：阻塞并返回失败原因，Claude 继续修复

控制 Stop Gate 行为：

```bash
# 规划阶段不执行门禁
entrix phase planning --repo .

# 开始实现后切换为门禁阶段
entrix phase implementation --repo .
```

阶段标记按工作区保存，默认 8 小时过期。

## Java 项目配置

### 并发控制

Entrix 只限制自身的外层检查并发，不解析或改写 Maven/Gradle 命令。

**Entrix 层面**（默认串行）：

```yaml
settings:
  max_parallel_producers: 1
```

```bash
entrix run --parallel --max-workers 2
```

**构建工具层面**（需要显式配置）：

对于 Java 多模块项目，必须限制构建工具的内部并发：

- Maven Reactor：`-T1`
- Maven Surefire/Failsafe：`-DforkCount=1 -DreuseForks=true`
- Gradle：`--max-workers=1`

示例 `harness.yaml`：

```yaml
fitness:
  dimensions:
    - dimension: java_build
      weight: 100
      threshold: {pass: 100, warn: 90}
      metrics:
        - name: compile_fast
          command: mvn -B -T1 -Dmaven.test.skip=true compile
          tier: fast
          hard_gate: true
        - name: tests_serial
          command: mvn -B -T1 -DforkCount=1 -DreuseForks=true test
          tier: normal
          hard_gate: true
```

### JVM 内存控制

`-Xmx256m` 只限制单个 JVM 堆内存，无法控制多个 fork 后的总内存。需要在 `pom.xml` 或 `build.gradle` 中配置：

**Maven（pom.xml）**：

```xml
<plugin>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <forkCount>1</forkCount>
    <reuseForks>true</reuseForks>
    <argLine>-Xmx256m</argLine>
  </configuration>
</plugin>
```

**Gradle（build.gradle）**：

```groovy
test {
    maxHeapSize = '256m'
    maxParallelForks = 1
}
```

这些项目内限制与 Entrix 的外层 worker 限制需要同时配置。

## Stop Gate 深度说明

### 调用契约

Stop Gate 通过 stdin 接收 JSON payload，在 stdout 输出裁决结果：

**输入格式（stdin）**：

```json
{
  "session_id": "session-123",
  "cwd": "/path/to/workspace"
}
```

**输出格式（stdout）**：

成功时（PASS）：空输出

失败时（FAIL/BLOCKED）：

```json
{
  "schema_version": "stop-gate-feedback/v1",
  "decision": "block",
  "reason": "Hard gates failed: API tests pass",
  "status": "fail",
  "summary": "Hard gates failed: API tests pass",
  "attempt_id": "session-123",
  "evidence_bundle_path": "/tmp/.../...bundle.json",
  "gates": [
    {
      "name": "API tests pass",
      "severity": "hard",
      "active": true,
      "passed": false,
      "message": "Failed for evidence api-test",
      "matched_evidence_id": "api-test"
    }
  ],
  "evidence": [
    {
      "id": "api-test",
      "type": "test",
      "name": "API tests",
      "status": "fail",
      "summary": {"total": 10, "passed": 9, "failed": 1},
      "artifacts": [{"type": "junit", "path": "artifacts/api.xml"}]
    }
  ],
  "collection_errors": [],
  "next_action": "fix_issues_and_retry"
}
```

### 缓存机制

- **PASS 从不缓存**：每次都重新收集证据
- **FAIL/BLOCKED/ERROR 可缓存**：当工作区内容、分支、base ref、`harness.yaml`、相关环境变量均未变化时，直接返回上次失败原因

### 手动测试

```bash
# 验证配置
entrix harness validate harness.yaml

# 手动运行完整 Harness
entrix harness run --config harness.yaml --json

# 模拟 Stop 事件
echo '{"session_id": "manual", "cwd": "'$PWD'"}' | entrix stop-gate
```

## Review Triggers

配置高风险变更自动升级规则：

```yaml
review_triggers:
  rules:
    - name: high_risk_directory_change
      type: changed_paths
      paths:
        - src/core/acp/**
        - src/core/orchestration/**
        - services/api/**
      severity: high
      action: require_human_review

    - name: oversized_change
      type: diff_size
      max_files: 12
      max_added_lines: 600
      max_deleted_lines: 400
      severity: medium
      action: require_human_review
```

运行：

```bash
entrix review-trigger --base HEAD~1
entrix review-trigger --base HEAD~1 --json
```

## CI 集成

### GitHub Actions

```yaml
name: Quality Gates

on: [push, pull_request]

jobs:
  entrix:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install Entrix
        run: pip install entrix

      - name: Validate configuration
        run: entrix harness validate harness.yaml

      - name: Run fast checks
        run: entrix run --tier fast --output report.json

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: entrix-report
          path: report.json
```

### 二进制插件分发

通过 GitHub Releases 分发的二进制插件独立于 CI 工件：

- **CI Artifacts**：临时构建产物，用于调试和审查
- **Release Assets**：经过测试的正式发布版本，用于生产环境

发布流程：

1. 构建多平台二进制文件
2. 创建 GitHub Release
3. 上传平台特定资产
4. 插件自动从 Release 下载对应平台版本

## 高级配置

### Evidence Producer 字段

```yaml
evidence_producers:
  - id: api-contract-test
    type: test
    name: API 契约测试
    command: pytest -q --junitxml=artifacts/api.xml
    producer: pytest
    parser:
      type: junit
      path: artifacts/api.xml
    artifacts:
      - type: junit
        path: artifacts/api.xml
    timeout_seconds: 120
    when:
      changed_files:
        - "src/api/**"
        - "openapi.yaml"
```

### Gate Policy 字段

```yaml
gate_policies:
  - name: API tests pass
    severity: hard
    rule:
      evidence_id: api-test
      condition: 'status == "pass"'
    when:
      env:
        CI: "true"
```

### Fitness Metric 高级字段

```yaml
metrics:
  - name: api_contract
    command: npm run test:contract 2>&1
    hard_gate: false
    tier: normal
    description: API 契约测试

    # 执行范围：local, ci, staging, prod_observation
    execution_scope: ci

    # 超时时间（秒）
    timeout_seconds: 120

    # 门禁严重级别：hard, soft, advisory
    gate: soft

    # 证据类型：command, test, probe, sarif, manual_attestation
    evidence_type: test

    # 置信度：high, medium, low, unknown
    confidence: high

    # 信号稳定性：deterministic, noisy
    stability: deterministic

    # 适应度类型：atomic 或 holistic
    kind: atomic

    # 分析模式：static 或 dynamic
    analysis: dynamic

    # 负责人
    owner: team-platform

    # 仅当这些文件变化时运行
    run_when_changed:
      - "src/api/**"
      - "openapi.yaml"

    # 临时豁免
    waiver:
      reason: "已知不稳定测试，问题 #42 跟踪修复"
      owner: team-platform
      tracking_issue: 42
      expires_at: "2025-06-01"
```

## CLI 参考

### 常用命令

```bash
# 初始化配置
entrix init --repo .
entrix init --repo . --profile auto
entrix init --repo . --profile java-maven

# 验证配置
entrix validate
entrix harness validate harness.yaml

# 运行检查
entrix run --tier fast
entrix run --tier normal
entrix run --tier normal --dimension code_quality
entrix run --changed-only --base HEAD~1
entrix run --metric eslint_pass --metric ts_typecheck_pass

# Review 触发器
entrix review-trigger --base HEAD~1
entrix review-trigger --base HEAD~1 --json

# 阶段控制
entrix phase planning --repo .
entrix phase implementation --repo .

# 手动 Stop Gate 测试
echo '{"session_id": "test", "cwd": "'$PWD'"}' | entrix stop-gate
```

### 输出格式

```bash
# JSON 报告
entrix run --tier fast --output report.json
entrix run --tier fast --output -  # stdout

# 可视化输出
entrix run --tier fast --format ascii  # 零依赖
entrix run --tier fast --format rich    # 需要 pip install entrix[visual]
```

### 并发控制

```bash
# 并行运行
entrix run --parallel --max-workers 2
entrix harness run --parallel --max-workers 2
```

## 图命令（可选）

需要 `pip install entrix[graph]`：

```bash
# 构建代码图
entrix graph build --base HEAD~1

# 影响分析
entrix graph impact --base HEAD~1 --depth 3

# 测试半径估计
entrix graph test-radius --base HEAD~1

# 结构查询
entrix graph query callers_of "mymodule.MyClass.my_method"
entrix graph query tests_for "src/core/engine.py" --json

# 审查上下文生成
entrix graph review-context --base HEAD~1 --json
```

## 文件分析

```bash
# 超大文件分析
entrix analyze long-file --files src/app.ts src/lib.ts
entrix analyze long-file --json
entrix analyze long-file --config file_budgets.json --strict-limit
```

## 故障排查

### Stop Gate 未触发

1. 检查 `harness.yaml` 是否存在
2. 查看状态：`entrix status --repo .`
3. 运行诊断：`entrix doctor --repo .`
4. 检查是否设置了 `ENTRIX_STOP_GATE_DISABLED=1`
5. 查看 Claude Code hooks 配置

### Stop Gate 一直重复阻断

1. 修复报告中的问题后，运行 `entrix stop-gate retry --repo . --session-id <session-id>` 清理当前 session 的缓存裁决
2. 阶段状态异常时运行 `entrix phase clear --repo . --session-id <session-id>`
3. 再次运行 `entrix status --repo . --session-id <session-id>` 确认缓存已清除

### 检查执行失败

1. 运行 `entrix harness validate harness.yaml`
2. 手动测试命令：`entrix run --tier fast --verbose`
3. 检查工作目录是否正确

### 二进制下载失败

1. 检查网络连接
2. 设置镜像：`ENTRIX_RELEASE_BASE_URL=https://your-mirror.com`
3. 使用本地文件：`ENTRIX_BINARY_PATH=/path/to/entrix-binary`
4. 如果提示 signature、manifest 或 checksum 校验失败，确认镜像完整同步了同版本的二进制、`.sha256`、`.sha256.sig`、`release-manifest.json` 和 `release-manifest.json.sig`

### Java 并发问题

1. 确认 Maven：`-T1 -DforkCount=1 -DreuseForks=true`
2. 确认 Gradle：`--max-workers=1`
3. 检查 Entrix：`max_parallel_producers: 1`

## 示例项目

Entrix 在 [`examples/`](./examples/) 下提供了可复制的示例：

- [`examples/file-length-hook/`](./examples/file-length-hook/)：pre-commit 文件预算 hook
- [`examples/frontend-quality-pack/`](./examples/frontend-quality-pack/)：前端质量门禁与 review-trigger 指南

## 项目结构

```text
entrix/
├── entrix/                  # Python 核心实现
│   ├── cli.py               # CLI 解析和命令编排
│   ├── engine.py            # Fitness 执行引擎
│   ├── model.py             # Metric、Report 和状态模型
│   ├── governance.py        # tier、scope、评分和执行策略
│   ├── harness/             # YAML 配置、Evidence、Producer、Gate
│   ├── stop_gate/           # Claude Code Stop Hook 和状态管理
│   ├── runners/             # shell、SARIF 和 graph 执行器
│   ├── structure/           # 语言结构分析和 graph adapter
│   ├── reporters/           # text、ASCII、Rich 和 JSON 报告
│   └── presets/              # 项目类型预设
├── bin/                     # 插件启动器和 Release 校验器
├── hooks/                   # Claude Code Hook 清单
├── skills/entrix/           # Entrix Skill、示例和规格
├── examples/                # 可复制的配置和 Hook 示例
├── scripts/                 # 发布、回归和文件预算脚本
├── tests/                   # 单元、集成、MCP、Harness 和 Stop Gate 测试
├── docs/                    # 使用指南、设计、ADR 和发布文档
├── harness.yaml             # 本仓库自身的质量门禁配置
├── pyproject.toml           # Python 包和开发工具配置
└── .claude-plugin/          # Claude Code 插件和 marketplace 清单
```

## 更多资源

- **架构决策**：[`docs/adr/README.md`](./docs/adr/README.md) — Entrix 架构决策与原理
- **本地插件调试**：[`docs/local-plugin-install.md`](./docs/local-plugin-install.md) — 本地源码插件和离线调试详细步骤
- **发布清单**：[`docs/release-checklist.md`](./docs/release-checklist.md) — 版本发布到双远程的完整时序与验证步骤
- **贡献指南**：[CONTRIBUTING.md](CONTRIBUTING.md)

## 本地开发

项目要求 Python 3.11+。从源码开发时建议创建隔离虚拟环境，并安装开发、MCP、graph 和 Rich 输出依赖：

```bash
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell：.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,mcp,graph,visual]"
```

标准验证命令：

```bash
ruff check .
pytest -q
mypy
python -m build --no-isolation
python -m entrix harness validate harness.yaml
python -m entrix harness run --config harness.yaml --json
```

本项目的覆盖率基线在 `pyproject.toml` 中设置为 75%。MCP 可选依赖的合同和 stdio 握手测试：

```bash
python -m pip install -e ".[dev,mcp]"
pytest tests/test_mcp_contract.py tests/test_mcp_stdio.py -q
```

## 开发者验证

发布前验证检查：

```bash
# 验证配置
entrix harness validate harness.yaml

# Markdown 链接检查
# （需要安装 markdown-link-check）

# Git 格式检查
git diff --check

# 运行回归测试
python -m pytest tests/ -q
```

## 项目状态

**当前状态**：

- 已在真实仓库工作流中稳定用于生产
- 可作为独立 PyPI 包安装
- 适用于 AI 辅助项目配置
- Claude Code 插件支持无 Python 二进制发行版

**当前边界**：

- 配置格式：根目录 `harness.yaml`
- 图命令需要可选依赖：`pip install entrix[graph]`
- 结构分析支持：Python、Rust、Go、Java、TypeScript/JavaScript
- 内部架构仍在向更清晰的核心/适配器/预设拆分演进

## 贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发指南和贡献流程。

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE)。
