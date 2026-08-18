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

## 安装

选择一种安装方式：

### Claude Code 插件（推荐）

```bash
/plugin marketplace add https://gitee.com/duxvfeng/entrix.git
/plugin install entrix@entrix
```

安装插件后请重启 Claude Code。

### 独立 CLI（`uv` 或 `pip`）

```bash
uv tool install entrix
# 或
pip install entrix

entrix --help
```

安装 CLI 后，如果希望在当前仓库中集成 Claude Code MCP：

```bash
entrix install --repo .
```

需要 Python 3.10+。`uv` 仅用于 `uv` / `uvx` 工作流。

<details>
<summary><strong>它能做什么</strong></summary>
<br>

- 将质量门禁和架构约束编码为可复用的护栏规格
- 按 `fast` / `normal` / `deep` 层级运行检查
- 基于 diff 运行变更感知检查，支持加权评分和硬门禁
- 通过 `review-trigger` 将高风险变更路由到更深入的验证
- 可选添加基于图的影响分析、测试半径和审查上下文分析

</details>

<details>
<summary><strong>变更生命周期中的护栏</strong></summary>
<br>

- 在风险代码落地前运行检查
- 每次运行都会生成证据
- 策略可以自动硬阻断、警告或升级至人工审查

</details>

## 生命周期视图

![Entrix 生命周期](https://gitee.com/duxvfeng/entrix/raw/main/docs/lifecycle.svg)

更多设计背景：

- `tools/entrix/docs/adr/README.md`：Entrix 架构决策与原理

## 术语

Entrix 使用**适应度（fitness）**的演进架构含义：适应度函数是一种可执行检查，用于衡量代码库是否仍然满足质量或架构目标。面向产品的语言中，你可以将其理解为版本化的质量护栏。

## 环境要求

- Python 3.10+
- 使用 `--base HEAD~1` 的命令需要在 Git 仓库上下文中运行

可选：

- `uv` 用于 `uv tool install ...` 和 `uvx ...`
- `pip install entrix[graph]` 用于图相关命令

## 高级安装

### 替代 CLI 调用方式

<details>
<summary><strong>CLI 调用选项</strong></summary>
<br>

```bash
uv tool install entrix
# 或
pip install entrix

uvx entrix --help
uvx entrix run --tier fast
uvx entrix run --tier normal --stream failures
uvx entrix run --tier normal --stream all
uvx entrix review-trigger --base HEAD~1
```

</details>

<details>
<summary><strong>可选 extras</strong></summary>
<br>

```bash
pip install entrix[graph]
pip install entrix[mcp]
pip install entrix[dev]

uvx entrix install --repo .
```

</details>

## 首次运行

### 1. 创建 Harness 配置

在项目根目录运行 `entrix init --repo .`，Entrix 会创建 `.mcp.json` 和唯一的
`harness.yaml`。`entrix run`、`entrix validate`、`entrix review-trigger` 与 Stop
Gate 都从该文件读取质量规则。

`entrix init` 只生成配置，不会执行校验、Fitness、Harness 或 Stop Gate。通过 Claude
Code 使用时，Claude 必须先询问是否继续运行检查；只有得到明确确认后才可执行下方命令。

Stop Gate 按任务阶段触发：头脑风暴和规划阶段使用 `entrix phase planning --repo .`，不执行
门禁；用户批准开始开发后使用 `entrix phase implementation --repo .`，实现阶段结束时执行
完整门禁。`entrix init` 会自动写入一次性初始化标记，当前初始化回合结束时跳过门禁。没有阶段
标记时，为兼容直接编辑工作流，工作区有变更仍会触发 Stop Gate；没有变更则直接放行。
阶段标记按工作区保存并默认 8 小时过期，不提供会话级隔离；并发会话或遗留规划标记存在时，
开始实现前必须显式切换到 `implementation`。

### 并发与 Java 多模块项目

Entrix 只限制自身同时启动的外层检查数量，不解析或改写 Maven、Surefire、Failsafe 或
Gradle 命令。默认 `entrix run` 和 `entrix harness run` 都串行执行；Stop Gate 始终串行。

手工执行 Harness 时，必须显式声明 `--parallel` 才会并行。实际 producer 数不超过
`harness.yaml` 中的 `settings.max_parallel_producers`，也不超过 CLI 的 `--max-workers`：

```yaml
settings:
  failure_mode: closed
  max_parallel_producers: 1
```

```bash
entrix harness run --parallel --max-workers 2
entrix run --parallel --max-workers 2
```

Java 多模块项目还需在检查命令中限制构建工具的内部并发。`-Xmx256m` 只限制单个 JVM 的
堆内存，不能限制多个 fork 后的总内存。Maven Reactor 使用 `-T1`，Surefire/Failsafe 使用
`forkCount=1` 与 `reuseForks=true`，Gradle 使用 `--max-workers=1`：

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

若 `pom.xml` 固定了 Surefire/Failsafe 配置，请在对应插件中设置相同值。Gradle 项目的测试
命令应形如 `./gradlew test --max-workers=1`。这些项目内限制与 Entrix 的外层 worker 限制需要
同时配置。

示例 `harness.yaml` 的 Fitness 段：

```yaml
version: "harness/v1"
settings:
  failure_mode: closed
fitness:
  dimensions:
    - dimension: code_quality
      weight: 100
      threshold: {pass: 90, warn: 80}
      metrics:
        - name: lint
          command: npm run lint 2>&1
          hard_gate: true
          tier: fast
          description: ESLint 必须通过。
        - name: unit_tests
          command: npm run test:run 2>&1
          pattern: "Tests\\s+\\d+\\s+passed"
          hard_gate: true
          tier: normal
          description: 单元测试必须通过。
review_triggers: {rules: []}
evidence_producers:
  - id: fitness
    type: fitness
    name: Entrix Fitness
    builtin: entrix-fitness
gate_policies:
  - name: Fitness must pass
    severity: hard
    rule: {evidence_id: fitness, condition: 'status == "pass"'}
```

### 高级指标字段

除了上述基本字段外，`fitness.dimensions[].metrics` 中的每个指标还支持更多选项：

```yaml
metrics:
  - name: api_contract
    command: npm run test:contract 2>&1
    hard_gate: false
    tier: normal
    description: API 契约测试

    # 执行范围 — 该指标在何处具有权威性
    # 取值：local, ci, staging, prod_observation
    execution_scope: ci

    # 超时时间（秒），null 表示无限制
    timeout_seconds: 120

    # 门禁严重级别：hard, soft, advisory
    gate: soft

    # 证据类型：command, test, probe, sarif, manual_attestation
    evidence_type: test

    # 置信度：high, medium, low, unknown
    confidence: high

    # 信号稳定性：deterministic, noisy
    stability: deterministic

    # 适应度类型：atomic（单一检查）或 holistic（系统范围）
    kind: atomic

    # 分析模式：static（代码结构）或 dynamic（运行时）
    analysis: dynamic

    # 该指标负责人
    owner: team-platform

    # 仅当这些文件模式发生变化时运行
    run_when_changed:
      - "src/api/**"
      - "openapi.yaml"

    # 临时豁免，用于绕过失败的指标
    waiver:
      reason: "已知不稳定测试，问题 #42 跟踪修复"
      owner: team-platform
      tracking_issue: 42
      expires_at: "2025-06-01"
```

### 2. 确认后运行检查

```bash
entrix run --tier fast
entrix run --tier normal
entrix run --tier normal --scope ci --dimension code_quality --dimension testability
entrix run --tier fast --metric eslint_pass --metric ts_typecheck_pass
entrix run --changed-only --base HEAD~1
entrix validate
```

使用 `--metric` 可以仅运行特定指标。使用 `--base HEAD~1` 的命令必须在具有有效 base revision 的 Git 仓库内运行。

### 3. 添加审查触发器

`review-trigger` 从 `harness.yaml` 的 `review_triggers.rules` 读取规则：

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

示例输出：

```json
{
  "human_review_required": true,
  "base": "HEAD~1",
  "changed_files": [
    "services/api/src/routes/acp_routes.rs"
  ],
  "diff_stats": {
    "file_count": 13,
    "added_lines": 936,
    "deleted_lines": 20
  },
  "triggers": [
    {
      "name": "high_risk_directory_change",
      "severity": "high",
      "action": "require_human_review",
      "reasons": [
        "changed path: services/api/src/routes/acp_routes.rs"
      ]
    }
  ]
}
```

## Claude Stop Gate

Entrix 包含 **Claude Stop Gate** —— 一个自动化 DoD 门禁系统。当 Claude 请求结束任务时，Stop Gate 会独立收集证据、按策略裁决，并决定是允许结束还是阻断并返回可执行的失败原因。

### 为什么需要 Stop Gate

AI 代理完成任务后请求停止时，传统上依赖代理自身判断质量。Stop Gate 引入了一个独立的审查层：

- **独立证据收集**：`EvidenceEngine` 按 `harness.yaml` 运行 producer，生成标准化的 `evidence/v1` 并保存为不可变的 Evidence Bundle
- **声明式裁决**：`GateEngine` 只消费 Evidence，按策略判定 `PASS` / `FAIL` / `BLOCKED`
- **默认拒绝（fail-closed）**：配置已启用时，配置错误、收集失败、存储失败或裁决异常都会阻止 Stop
- **失败即反馈**：FAIL 时返回按 Gate 组织的结构化反馈，包含失败 Evidence、artifact 路径和下一步动作，Claude 可据此继续修复

### 调用流程

```text
Claude 编码完成 → 请求 Stop
        ↓
Claude Code 触发 hooks/hooks.json 中的 Stop hook
        ↓
bash hooks/stop-gate.sh → entrix stop-gate
        ↓
读取 stdin payload、阶段状态、harness.yaml
        ↓
EvidenceEngine 独立收集证据 → EvidenceStore 保存 Bundle
        ↓
GateEngine 按 gate_policies 仲裁
        ↓
PASS: 空 stdout → Claude 允许结束
FAIL/BLOCKED/ERROR: stdout 输出 {"decision":"block", ...} → Claude 继续修改
        ↓
Claude 修复后再次 Stop → Harness 重新验证
```

### 核心组件

```text
entrix/stop_gate/
├── hook.py          # Claude Code Stop hook 入口与缓存/重验逻辑
├── runner.py        # HarnessRunner：编排 EvidenceEngine + GateEngine
├── feedback.py      # 将 Verdict + EvidenceBundle 格式化为结构化 block JSON
├── revalidation.py  # StopGateStateStore：按工作区指纹缓存 FAIL/BLOCKED
├── phase.py         # 工作区阶段标记（planning / implementation / init）
├── model.py         # 历史数据模型（保留，供下游使用）
hooks/
├── hooks.json       # Claude Code 插件 hook 注册
└── stop-gate.sh     # 查找 entrix/uvx/python3 的包装脚本
```

### 在 Claude 中安装与使用

#### 1. 安装插件（推荐）

```bash
/plugin marketplace add https://gitee.com/duxvfeng/entrix.git
/plugin install entrix@entrix
```

安装后重启 Claude Code。插件通过 `hooks/hooks.json` 自动注册 `Stop` hook，无需额外配置。

#### 2. 或独立 CLI

```bash
pip install entrix
# 或
uv tool install entrix
```

如果要在当前仓库接入 Claude Code MCP（主动工具调用通道）：

```bash
entrix install --repo .
```

> 注意：`entrix serve` 是 MCP 主动工具通道，与任务结束时的 Stop hook 是两条独立链路。

#### 3. 初始化 Harness 配置

Stop Gate 只在存在 `harness.yaml` 或 `.harness/harness.yaml` 的仓库激活。生成最小配置：

```bash
entrix init --repo .
```

这会创建 `harness.yaml`。一个最小严格配置示例：

```yaml
version: "harness/v1"
settings: {failure_mode: closed}

evidence_producers:
  - id: api-test
    type: test
    name: API tests
    command: pytest -q --junitxml=artifacts/api.xml
    producer: pytest
    parser: {type: junit, path: artifacts/api.xml}
    artifacts:
      - type: junit
        path: artifacts/api.xml

gate_policies:
  - name: API tests pass
    severity: hard
    rule: {evidence_id: api-test, condition: 'status == "pass"'}
```

配置说明：

- `settings.failure_mode` 只接受 `closed`，省略也按 `closed` 处理
- 至少需要一个 producer 和一个 gate policy
- producer 支持 `exit_code`、`regex`、`junit`、`json`、`evidence_json`、`sarif` 六种 parser
- `when` 可出现在 Harness、producer、gate 三个层级，控制何时激活

#### 4. 在 Claude 中使用

插件安装并配置 `harness.yaml` 后，Stop Gate 自动生效：

1. Claude 完成修改并尝试结束任务
2. Claude Code 自动调用 `entrix stop-gate`
3. Entrix 独立运行 producer 收集证据，Gate 裁决
4. **PASS**：Claude 正常结束
5. **FAIL / BLOCKED / ERROR**：Claude 收到失败原因，继续修复后再次尝试结束

可以通过阶段标记控制是否执行门禁：

```bash
# 头脑风暴/规划阶段不执行门禁
entrix phase planning --repo .

# 用户批准开发后切换为实现阶段
entrix phase implementation --repo .
```

阶段标记按工作区保存，默认 8 小时过期；并发会话不隔离。开始实现前必须显式切换到 `implementation`。

紧急旁路（会写入 stderr 审计警告）：

```bash
ENTRIX_STOP_GATE_DISABLED=1  # 环境变量，Claude 结束时不执行门禁
```

#### 5. 手动测试

```bash
# 验证配置
entrix harness validate harness.yaml

# 手动运行完整 Harness
entrix harness run --config harness.yaml --json

# 模拟 Claude Stop 事件
echo '{"session_id": "manual", "cwd": "'$PWD'"}' | entrix stop-gate
```

### 阻断反馈格式

失败时，`entrix stop-gate` 在 stdout 输出结构化 JSON：

```json
{
  "schema_version": "stop-gate-feedback/v1",
  "decision": "block",
  "reason": "Hard gates failed: API tests pass",
  "status": "fail",
  "summary": "Hard gates failed: API tests pass",
  "attempt_id": "manual",
  "evidence_bundle_path": "/tmp/harness-monitor/stop-gate/.../...-bundle.json",
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

Claude 看到 `decision: block` 和具体失败项后，可以继续修改代码，再次 Stop 时 Harness 会重新验证。

### 缓存与重验

- **PASS 从不缓存**：每次 Stop 都重新收集证据，确保放行基于最新状态
- **FAIL / BLOCKED / ERROR 可缓存**：当工作区内容、分支、base ref、`harness.yaml`、`when.env` 引用的环境变量均未变化时，直接返回上次失败原因，避免重复执行慢检查
- 任一相关输入变化后，缓存失效并重新取证

### 裁决规则

- **PASS**：所有 active gate 通过，无 hard/blocked 失败 → 允许停止
- **FAIL**：hard gate 不满足条件 → 阻止停止，需要修复后重试
- **BLOCKED**：证据缺失、blocked gate 触发或配置异常 → 阻止停止，需要人工干预或修复环境
- **ERROR**：收集、存储或裁决过程异常 → 按 fail-closed 阻止停止

### 测试

```bash
# 运行 Stop Gate 相关测试
python -m pytest tests/stop_gate/ -v

# 运行全量测试
python -m pytest tests/ -q
```

## 从 Routa.js 检出中开发

如果你使用的是 vendored 在 Routa.js monorepo 中的 `entrix` 副本，当前仓库工作流为：

```bash
pip install -e tools/entrix

PYTHONPATH=tools/entrix python3 -m entrix --help
PYTHONPATH=tools/entrix python3 -m entrix run --tier fast
PYTHONPATH=tools/entrix python3 -m entrix review-trigger --base HEAD~1
```

本仓库中的大多数本地 hook 和辅助脚本都使用 `PYTHONPATH=tools/entrix python3 -m entrix ...` 形式，以便可以直接从 monorepo 检出运行，无需单独安装全局二进制文件。

## 从源码开发本包

如果你正在处理 `entrix` 包本身的源码，请克隆本仓库并从仓库根目录安装。

从仓库根目录：

```bash
git clone https://gitee.com/duxvfeng/entrix.git
cd entrix
uv pip install -e .
```

使用 `pip`：

```bash
git clone https://gitee.com/duxvfeng/entrix.git
cd entrix
pip install -e .
```

## CLI 参考

大多数仓库只需要这三个命令：

- `entrix run`：执行 `harness.yaml` 中的 Fitness 护栏检查
- `entrix validate`：验证护栏配置
- `entrix review-trigger`：将高风险 diff 升级至人工审查

使用 `entrix analyze long-file` 进行超大文件结构分析，使用 `entrix graph ...` 进行基于图的影响分析。

## 示例包

Entrix 在 [`examples/`](./examples/) 下提供了可复制示例：

- [`examples/file-length-hook/`](./examples/file-length-hook/)：pre-commit 文件预算 hook
- [`examples/frontend-quality-pack/`](./examples/frontend-quality-pack/)：分层前端质量门禁与 review-trigger 指南

### `entrix run`

从 `harness.yaml` 的 `fitness.dimensions` 加载基于维度的护栏检查。

常用标志：

```bash
entrix run --tier fast
entrix run --parallel
entrix run --dry-run
entrix run --verbose
entrix run --format ascii
entrix run --format rich
entrix run --changed-only --base HEAD~1
entrix run --files src/app.ts src/lib.ts
entrix run --output report.json
entrix run --output -              # JSON 输出到 stdout
entrix run --min-score 90
```

使用 `--output` 将 JSON 报告写入文件（或 `-` 输出到 stdout），便于 CI 收集产物。使用 `--files` 传递显式变更文件列表以进行增量指标选择。使用 `--format ascii` 获取零依赖的可视化评分卡，或在安装了 `rich` 时使用 `--format rich` 获得更丰富的终端渲染（`pip install entrix[visual]`）。

### `entrix install` / `entrix init`

为目标仓库生成 Claude Code MCP 集成的 `.mcp.json` 与唯一的 `harness.yaml`。
`entrix init` 默认使用 `--profile auto` 根据仓库标记选择语言模板；未知仓库回退到
`generic`，检测到多个语言时要求显式选择。初始化只写文件，不执行检查。

```bash
entrix install --repo .
entrix init --dry-run
entrix init --profile python
entrix init --profile java-maven
entrix init --profile java-gradle
```

支持的 profile 为 `generic`、`python`、`node-typescript`、`java-maven`、
`java-gradle`、`go` 和 `rust`。Java 模板将 Maven Reactor、Surefire/Failsafe
或 Gradle worker 限制为单路；这只控制模板命令的内部并发，仍需结合项目自身的
JVM 内存设置。初始化完成并得到用户明确同意后，再运行配置校验或本地检查：

```bash
entrix harness validate harness.yaml
entrix run --tier fast
```

### `entrix serve`

通过 stdio 运行 Entrix MCP 服务器。

```bash
entrix serve
```

### `entrix validate`

检查 `harness.yaml` 的维度权重、review 规则、producer 与 gate policy。

```bash
entrix validate
entrix harness validate harness.yaml
```

### `entrix review-trigger`

评估面向治理的风险变更触发规则。

常用标志：

```bash
entrix review-trigger --base HEAD~1
entrix review-trigger --json
entrix review-trigger --fail-on-trigger
entrix review-trigger --config harness.yaml
```

### `entrix analyze long-file`

对超大或显式指定的源文件进行结构分析。返回 ClassMap / FunctionMap 载荷，展示类、方法、独立函数及其行范围。

支持语言：Python、Rust、Go、Java、TypeScript/JavaScript（包括 `tsx` / `jsx` 文件）。

```bash
entrix analyze long-file --files src/app.ts src/lib.ts
entrix analyze long-file --json
entrix analyze long-file --config file_budgets.json --strict-limit
entrix analyze long-file --min-lines 100
```

未提供 `--files` 时，自动发现超出配置行预算的文件。

### `entrix graph ...`

基于图的命令支持构建代码图、查询关系、影响分析、测试半径估计、提交历史分析以及面向 AI 的审查上下文生成。

需要可选的图依赖：`pip install entrix[graph]`。

#### `entrix graph build`

构建或更新代码图。

```bash
entrix graph build --base HEAD~1
entrix graph build --build-mode full --json
```

#### `entrix graph stats`

显示图统计信息（节点和边数量）。

```bash
entrix graph stats
entrix graph stats --json
```

#### `entrix graph impact`

分析变更文件的爆炸半径。

```bash
entrix graph impact --base HEAD~1
entrix graph impact --base HEAD~1 --depth 3 --json
```

#### `entrix graph test-radius`

估计受变更文件影响的测试。

```bash
entrix graph test-radius --base HEAD~1
entrix graph test-radius --base HEAD~1 --max-targets 50 --json
```

#### `entrix graph query`

针对代码图运行结构查询。

可用模式：`callers_of`、`callees_of`、`imports_of`、`importers_of`、`children_of`、`tests_for`、`inheritors_of`、`file_summary`。

```bash
entrix graph query callers_of "mymodule.MyClass.my_method"
entrix graph query tests_for "src/core/engine.py" --json
```

#### `entrix graph history`

使用当前图估计近期提交的测试半径。

```bash
entrix graph history --count 20 --ref main
entrix graph history --json
```

#### `entrix graph review-context`

从当前图构建面向 AI 的审查上下文。

```bash
entrix graph review-context --base HEAD~1 --json
entrix graph review-context --base HEAD~1 --max-files 20 --no-source
entrix graph review-context --base HEAD~1 --output context.json
```

## 预设系统

Entrix 使用预设系统来适应不同的项目布局。Harness 配置始终由项目根目录的 `harness.yaml`（或 `.harness/harness.yaml`）提供；预设不再决定质量配置的位置。

自定义预设可以覆盖：

- `should_ignore_changed_file(file_path)` — 过滤无关变更文件
- `domains_from_files(files)` — 从变更文件路径提取域标签

内置的 `RoutaPreset` 作为 monorepo 布局的参考实现。

## 面向 AI 的创作建议

如果 AI 代理正在生成或更新护栏规格，以下约定效果最佳：

- 每个维度在 `harness.yaml` 的 `fitness.dimensions` 中有一个条目
- 相关检查放在该条目的 `metrics` 列表中
- 优先使用稳定的命令输出，而非脆弱的文本匹配
- 仅在失败确实应该阻塞进度时使用 `hard_gate: true`
- 将 review-trigger 规则与评分指标分开

配置布局：

推荐文件布局：

```text
your-project/
  harness.yaml
```

新仓库初始化只创建配置：

```bash
entrix init --repo .
```

确认需要校验后，再运行：

```bash
entrix harness validate harness.yaml
entrix run --tier fast
```

启动创作规则：

- 保持默认本地 `entrix run` 在新机器上为绿色
- 如果某个命令仅在 CI 或预配置环境中具有权威性，请使用 `execution_scope: ci` 建模，而不是放在默认本地路径中
- 一致地更新每个现有代理入口文档：`AGENTS.md`、`CLAUDE.md` 或两者
- 如果两者都不存在，则仅创建 `AGENTS.md`

推荐启动策略：

- 初始化完成的标志是配置文件已创建；仅在用户明确要求校验时，才以 `entrix harness validate harness.yaml` 和普通本地 `entrix run` 作为检查完成标志
- 默认本地运行应由仓库安全包装器或廉价冒烟检查支持
- 将权威但需预配置的检查移入 `execution_scope: ci`
- 将 `AGENTS.md` 和 `CLAUDE.md` 的可发现性视为启动的一部分，而非可选的后续清理

本仓库还附带一个打包技能 `skills/entrix/`，供需要生成或修复 `harness.yaml` 的代理使用。该技能遵循上述相同的启动规则，并针对多个真实仓库进行验证。

## Skill 回归测试工具

捆绑的 `/entrix` skill 提供两种回归模式：

```bash
bash scripts/skill_regression.sh --fixtures
bash scripts/skill_regression.sh /abs/path/to/repo-a /abs/path/to/repo-b
```

- `--fixtures` 验证 `tests/fixtures/skill_regression/` 下的打包仓库配置
- 路径模式将打包技能注入每个目标仓库，运行 `claude -p /entrix`，然后使用 `entrix validate`、`entrix run --dry-run`、`entrix run --tier fast` 和普通 `entrix run` 验证结果

在 CI 中使用 fixture 模式，在发布技能变更前使用路径模式对真实仓库进行本地前向验证。

## Python API

### Stop Gate 示例

```python
import io
import json
from pathlib import Path

from entrix.stop_gate.hook import run_stop_gate_hook

payload = json.dumps({"session_id": "session-1", "cwd": str(Path.cwd())})
output = io.StringIO()

rc = run_stop_gate_hook(
    input_stream=io.StringIO(payload),
    output_stream=output,
)

print(f"exit_code={rc}")
result = output.getvalue()
if result:
    decision = json.loads(result)
    print(decision["decision"])   # "block" 或不存在
    print(decision["reason"])     # 失败原因
    print(decision.get("gates"))  # Gate 详情
```

如果需要直接调用 Harness runner：

```python
from pathlib import Path

from entrix.harness.config import load_harness_config
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.conditions import WhenContext
from entrix.harness.gate.arbiter import GateEngine
from entrix.harness.store import EvidenceStore

config = load_harness_config(Path("harness.yaml"))
context = HarnessRunContext(
    task_id="manual",
    repo_root=Path.cwd(),
    when_context=WhenContext(
        repo_root=Path.cwd(),
        changed_files=["src/main.py"],
        current_branch="main",
    ),
    store=EvidenceStore(Path.cwd()),
)
bundle = EvidenceEngine(config).collect(context)
verdict = GateEngine(config.gate_policies).arbitrate(bundle, context.when_context)
print(verdict.status.value)
```

### Review trigger 示例

```python
from pathlib import Path

from entrix.review_trigger import (
    collect_changed_files,
    collect_diff_stats,
    evaluate_review_triggers,
)
from entrix.harness.config import load_harness_config

repo_root = Path(".").resolve()
rules = load_harness_config(repo_root / "harness.yaml").review_trigger_rules
changed_files = collect_changed_files(repo_root, "HEAD~1")
diff_stats = collect_diff_stats(repo_root, "HEAD~1")
report = evaluate_review_triggers(rules, changed_files, diff_stats, base="HEAD~1")
print(report.to_dict())
```

### Fitness 规格加载示例

```python
from pathlib import Path

from entrix.harness.config import load_harness_config

dimensions = load_harness_config(Path("harness.yaml")).fitness_dimensions
for dimension in dimensions:
    print(dimension.name, len(dimension.metrics))
```

## 推荐的 Hook 集成

对于通用仓库，一个实用的模式是：

- `pre-commit`：先运行 `entrix hook file-length`，然后快速 lint
- `pre-push`：运行完整检查，然后打印 review-trigger 警告
- CI：运行 `entrix run` 并发布 JSON/报告输出

这样可以在早期通过自动化捕获确定性失败，同时将模糊的高风险变更升级给人类处理。

### 当前 Routa.js hook 布局

当前 Routa.js monorepo 故意使用略有不同的拆分：

- `pre-commit`：`npm run lint`
- `post-commit`：`PYTHONPATH=tools/entrix python3 -m entrix hook file-length --config tools/entrix/file_budgets.pre_commit.json --strict-limit ...` 作为仅警告的预算报告
- `pre-push`：`./scripts/smart-check.sh`，运行精选的 `entrix run --metric ...` 集合，然后评估 `review-trigger`

这样保持了提交时摩擦较低，同时仍能暴露文件预算漂移并在推送前强制执行高信号的适应度门禁。

## Submodule 升级指南

如果 Entrix 作为 git submodule vendored 到更大的仓库中：

- 首先从干净的 `tools/entrix` worktree 推送 Entrix 发布提交
- 在单独的提交中更新 superproject 指针
- 优先使用干净的 superproject 分支或 worktree 进行指针升级，以免无关的应用适应度 hook 阻塞纯粹的 submodule 更新

这样可以将 Entrix 发布和 superproject 指针升级作为独立的变更进行审查。

### 可复用的文件长度护栏

`entrix` 现在暴露了一个可复用的 hook 入口：

```bash
python3 -m entrix hook file-length \
  --config tools/entrix/file_budgets.pre_commit.json \
  --staged-only \
  --strict-limit
```

用于在 `pre-commit` 期间获得 AI 友好的超大文件失败，例如：

```text
current file length 2383 exceeds limit 1600: src/app/page.tsx
```

可复制的模板位于 [`examples/file-length-hook/`](examples/file-length-hook/)。

## 项目状态

当前状态：

- 已在真实仓库工作流中稳定用于生产
- 可作为独立 PyPI 包安装
- 适用于 AI 辅助项目配置

当前边界：

- 默认创作格式为根目录的 `harness.yaml`
- 图命令需要可选的图依赖：`pip install entrix[graph]`
- 当前检出中的公共 CLI 暴露 `run`、`validate`、`review-trigger`、`hook`、`analyze` 和 `graph`
- `analyze long-file` 结构分析支持 Python、Rust、Go、Java、TypeScript 和 JavaScript
- 内部架构仍在向更清晰的核心 / 适配器 / 预设拆分演进

## 贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发指南和贡献流程。

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE)。
