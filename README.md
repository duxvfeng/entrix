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
/plugin marketplace add https://gitee.com/duxvfeng/entrix/repository/archive/main.zip
/plugin install entrix@entrix
```

安装插件后请重启 Claude Code。

> 注意：部分 Claude Code 版本可能不支持 Gitee 源直接安装。如果提示 "source type ... does not support"，请改用下面的[手动配置方式](docs/local-plugin-install.md)。

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

### 1. 创建护栏规格

默认情况下，`entrix run` 会在当前项目的以下位置查找规格：

```text
docs/fitness/*.md
```

当存在 `docs/fitness/manifest.yaml` 时，Entrix 会将其作为权威来源。这允许使用嵌套的证据文件，例如 `docs/fitness/runtime/observability.md` 和 `docs/fitness/runtime/performance.md`。

示例 `docs/fitness/code-quality.md`：

```yaml
---
dimension: code_quality
weight: 20
threshold:
  pass: 90
  warn: 80
metrics:
  - name: lint
    command: npm run lint 2>&1
    hard_gate: true
    tier: fast
    description: ESLint 必须通过

  - name: unit_tests
    command: npm run test:run 2>&1
    pattern: "Tests\\s+\\d+\\s+passed"
    hard_gate: true
    tier: normal
    description: 单元测试必须通过
---

# 代码质量

叙事性证据、规则和归属说明可以放在 frontmatter 下方。
```

### 高级指标字段

除了上述基本字段外，frontmatter 中的每个指标还支持更多选项：

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

### 2. 运行检查

```bash
entrix run --tier fast
entrix run --tier normal
entrix run --tier normal --scope ci --dimension code_quality --dimension testability
entrix run --tier fast --metric eslint_pass --metric ts_typecheck_pass
entrix run --changed-only --base HEAD~1
entrix validate
```

使用 `--metric` 可以在不创建临时维度文件的情况下仅运行特定指标。使用 `--base HEAD~1` 的命令必须在具有有效 base revision 的 Git 仓库内运行。

### 3. 添加审查触发器

默认情况下，`review-trigger` 会加载当前项目的：

```text
docs/fitness/review-triggers.yaml
```

示例 `docs/fitness/review-triggers.yaml`：

```yaml
review_triggers:
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

## Claude Stop Gate（新增）

Entrix 现在包含 **Claude Stop Gate** —— 一个自动化质量门禁系统，用于在 Claude 请求结束任务时独立收集证据并做出是否允许停止的裁决。

### 为什么需要 Stop Gate

AI 代理在完成任务后请求停止时，传统上依赖代理自身判断质量。Stop Gate 引入了一个独立的审查层：

- **独立证据收集**：在 Claude 进程之外运行 Entrix fitness 检查和 review-trigger
- **无偏裁决**：基于收集到的证据自动判定 PASS / FAIL / BLOCKED
- **可操作反馈**：生成用户可读的 Markdown 反馈和机器可解析的 JSON 指令
- **状态持久化**：使用内存+文件系统的混合状态管理，支持中断恢复

### 核心组件

```text
entrix/stop_gate/
├── adapter.py      # Claude Code 插件接口
├── engine.py       # 核心编排引擎
├── collector.py    # 证据收集器
├── arbiter.py      # 门禁裁决器
├── formatter.py    # 反馈格式化器
├── state_manager.py # 会话状态管理器
├── hook.py         # Claude Code Stop hook 入口
├── model.py        # 核心数据模型
└── errors.py       # 错误处理系统
```

### 插件 Hook 集成（自动生效）

安装 Claude Code 插件后，Stop Gate 通过 `hooks/hooks.json` 注册的 `Stop` hook 自动接管任务结束裁决，无需手动配置：

- **仅对配置了 `docs/fitness/` 的仓库激活**——未配置的仓库直接放行，插件可以放心全局安装
- Claude 请求结束任务时，hook 独立收集证据并裁决：PASS 放行，FAIL/BLOCKED 以 `{"decision": "block", "reason": ...}` 阻止停止并把失败原因回传给 Claude 继续修复
- 内置防循环保护（`stop_hook_active`）与禁用开关（`export ENTRIX_STOP_GATE_DISABLED=1`）
- 优先使用 PATH 上的 `entrix`，其次 `uvx entrix`，最后回退到插件内的源码副本；全部不可用时放行

手动测试 hook 行为：

```bash
echo "{\"session_id\": \"t\", \"cwd\": \"$PWD\"}" | entrix stop-gate
```

### 快速使用

```python
from entrix.stop_gate import StopGateAdapter
from pathlib import Path

adapter = StopGateAdapter()

decision = adapter.on_before_stop({
    "session_id": "current-session",
    "task_id": "current-task",
    "workspace": Path.cwd(),
    "changed_files": ["src/main.py", "tests/test_main.py"],
    "stop_reason": "agent_completed",
})

if decision.allow_stop:
    print("✅ 质量检查通过，可以结束任务")
else:
    print(f"❌ {decision.feedback}")
```

### 裁决规则

- **PASS**：所有检查通过，无硬门禁失败，无人工审查要求 → 允许停止
- **FAIL**：硬门禁失败或分数不足 → 阻止停止，需要修复后重试
- **BLOCKED**：证据缺失或需要人工审查 → 阻止停止，需要人工干预

### 测试

```bash
# 运行 Stop Gate 单元测试
python -m pytest tests/stop_gate/ -v

# 运行端到端集成测试
python -m pytest tests/stop_gate/test_integration.py -v -m integration
```

更多详情见 [docs/stop-gate-usage.md](docs/stop-gate-usage.md)。

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

- `entrix run`：执行 `docs/fitness/*.md` 中的护栏检查
- `entrix validate`：验证护栏配置
- `entrix review-trigger`：将高风险 diff 升级至人工审查

使用 `entrix analyze long-file` 进行超大文件结构分析，使用 `entrix graph ...` 进行基于图的影响分析。

## 示例包

Entrix 在 [`examples/`](./examples/) 下提供了可复制示例：

- [`examples/file-length-hook/`](./examples/file-length-hook/)：pre-commit 文件预算 hook
- [`examples/frontend-quality-pack/`](./examples/frontend-quality-pack/)：分层前端质量门禁与 review-trigger 指南

### `entrix run`

从 `docs/fitness/*.md` 加载基于维度的护栏检查。

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

为目标仓库生成 Claude Code MCP 集成的 `.mcp.json`。

```bash
entrix install --repo .
entrix init --dry-run
```

### `entrix serve`

通过 stdio 运行 Entrix MCP 服务器。

```bash
entrix serve
```

### `entrix validate`

检查维度权重是否总和为 `100%`。

```bash
entrix validate
```

### `entrix review-trigger`

评估面向治理的风险变更触发规则。

常用标志：

```bash
entrix review-trigger --base HEAD~1
entrix review-trigger --json
entrix review-trigger --fail-on-trigger
entrix review-trigger --config docs/fitness/review-triggers.yaml
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

Entrix 使用预设系统来适应不同的项目布局。默认 `ProjectPreset` 在 `docs/fitness/` 中查找护栏规格，在 `docs/fitness/review-triggers.yaml` 中查找审查触发器。

自定义预设可以覆盖：

- `fitness_dir(project_root)` — 护栏规格文件位置
- `review_trigger_config(project_root)` — review trigger YAML 路径
- `should_ignore_changed_file(file_path)` — 过滤无关变更文件
- `domains_from_files(files)` — 从变更文件路径提取域标签

内置的 `RoutaPreset` 作为 monorepo 布局的参考实现。

## 面向 AI 的创作建议

如果 AI 代理正在生成或更新护栏规格，以下约定效果最佳：

- 每个文件一个维度
- frontmatter 可执行，正文用于解释
- 优先使用稳定的命令输出，而非脆弱的文本匹配
- 仅在失败确实应该阻塞进度时使用 `hard_gate: true`
- 将 review-trigger 规则与评分指标分开
- 将 markdown 视为叙事层，而非唯一的结构来源

推荐文件布局：

```text
your-project/
  docs/
    fitness/
      README.md
      manifest.yaml
      code-quality.md
      security.md
      runtime/
        observability.md
        performance.md
      review-triggers.yaml
```

新仓库最小启动流程：

```bash
mkdir -p docs/fitness
cat > docs/fitness/code-quality.md <<'EOF'
---
dimension: code_quality
weight: 100
threshold:
  pass: 100
  warn: 80
metrics:
  - name: lint
    command: npm run lint 2>&1
    hard_gate: true
    tier: fast
---

# Code Quality
EOF

entrix validate
entrix run --tier fast
```

启动创作规则：

- 保持默认本地 `entrix run` 在新机器上为绿色
- 如果某个命令仅在 CI 或预配置环境中具有权威性，请使用 `execution_scope: ci` 建模，而不是放在默认本地路径中
- 一致地更新每个现有代理入口文档：`AGENTS.md`、`CLAUDE.md` 或两者
- 如果两者都不存在，则仅创建 `AGENTS.md`

推荐启动策略：

- 不要停留在看似合理的草稿；启动完成的标志是本地 `entrix validate` 和普通本地 `entrix run` 均通过
- 默认本地运行应由仓库安全包装器或廉价冒烟检查支持
- 将权威但需预配置的检查移入 `execution_scope: ci`
- 将 `AGENTS.md` 和 `CLAUDE.md` 的可发现性视为启动的一部分，而非可选的后续清理

本仓库还附带一个打包技能 `skills/entrix/`，供需要自动生成或修复 `docs/fitness/` 的代理使用。该技能遵循上述相同的启动规则，并针对多个真实仓库进行验证。

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
from pathlib import Path

from entrix.stop_gate import StopGateAdapter

adapter = StopGateAdapter()

decision = adapter.on_before_stop({
    "session_id": "session-1",
    "task_id": "task-1",
    "workspace": Path.cwd(),
    "changed_files": ["src/main.py"],
    "stop_reason": "agent_completed",
})

print(decision.allow_stop)
print(decision.feedback)
```

### Review trigger 示例

```python
from pathlib import Path

from entrix.review_trigger import (
    collect_changed_files,
    collect_diff_stats,
    evaluate_review_triggers,
    load_review_triggers,
)

repo_root = Path(".").resolve()
rules = load_review_triggers(repo_root / "docs" / "fitness" / "review-triggers.yaml")
changed_files = collect_changed_files(repo_root, "HEAD~1")
diff_stats = collect_diff_stats(repo_root, "HEAD~1")
report = evaluate_review_triggers(rules, changed_files, diff_stats, base="HEAD~1")
print(report.to_dict())
```

### Fitness 规格加载示例

```python
from pathlib import Path

from entrix.evidence import load_dimensions

dimensions = load_dimensions(Path("docs/fitness"))
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

- 默认创作格式为 `docs/fitness/` 下的 markdown frontmatter
- 图命令需要可选的图依赖：`pip install entrix[graph]`
- 当前检出中的公共 CLI 暴露 `run`、`validate`、`review-trigger`、`hook`、`analyze` 和 `graph`
- `analyze long-file` 结构分析支持 Python、Rust、Go、Java、TypeScript 和 JavaScript
- 内部架构仍在向更清晰的核心 / 适配器 / 预设拆分演进

## 贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发指南和贡献流程。

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE)。
