# Entrix 单文件 Harness 配置实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让 `entrix init` 创建唯一的 `harness.yaml`，并使 Fitness、review trigger、Harness 与 Stop Gate 只从该文件读取配置。

**架构：** `load_harness_config()` 解析内联 Fitness dimensions 和 review trigger rules，返回领域对象。CLI、内置 producer 与 Stop Hook 共享该配置；`docs/fitness/`、manifest 和独立 review trigger 文件全部移除且不再读取。

**技术栈：** Python 3.11+、dataclasses、PyYAML、argparse、pytest、Ruff、mypy、Hatchling。

---

## 文件结构

- 创建 `entrix/harness/template.py`：默认配置数据与稳定 YAML 序列化。
- 创建 `entrix/harness/fitness.py`：内联 mapping 到 `Dimension`/`Metric` 的验证与转换。
- 修改 `entrix/harness/config.py`：提供 `fitness_dimensions`、`review_trigger_rules`。
- 修改 `entrix/review_trigger.py`：提供内联 rule 解析，删除文件读取入口。
- 修改 `entrix/engine.py`、`entrix/harness/engine.py`、`entrix/harness/producers/builtin.py`：只接收已解析领域对象。
- 修改 `entrix/cli.py`、`entrix/stop_gate/hook.py`、`entrix/stop_gate/runner.py`：配置驱动 CLI/Hook、`init --force` 和命令导览。
- 删除 `entrix/loaders/evidence_loader.py`、`docs/fitness/`，迁移 `examples/frontend-quality-pack/`、`tests/fixtures/skill_regression/`、`skills/entrix/` 与引用文档。
- 修改 `tests/harness/`、`tests/test_cli.py`、`tests/test_harness_cli.py`、`tests/stop_gate/`；创建 `tests/harness/test_template.py`。

### 任务 1：解析单文件领域配置

**文件：** 创建 `entrix/harness/fitness.py`；修改 `entrix/harness/config.py`、`entrix/review_trigger.py`、`tests/harness/test_config.py`、`tests/test_review_trigger.py`。

- [ ] 先写 `test_load_harness_config_builds_inline_fitness_and_review_rules`：给临时 `harness.yaml` 写入 `fitness.dimensions`、一个 metric 和 `review_triggers.rules`，断言 `config.fitness_dimensions[0].metrics[0].name == "lint"` 以及 `config.review_trigger_rules[0].name == "sensitive"`。
- [ ] 运行 `python -m pytest tests/harness/test_config.py::test_load_harness_config_builds_inline_fitness_and_review_rules -q`；预期因字段不存在失败。
- [ ] 实现 `parse_dimensions(raw: object) -> list[Dimension]`，将 `tier`、`execution_scope`、`gate`、`kind`、`analysis`、`stability`、`evidence_type`、`confidence` 转为既有枚举；拒绝非列表、重复 dimension/metric、空 command/name 和非法枚举。实现 `parse_review_trigger_rules(raw_rules: object) -> list[ReviewTriggerRule]`，承接当前 `load_review_triggers()` 的 mapping 转换但不接受文件路径。
- [ ] 在 `HarnessConfig` 添加：

```python
fitness_dimensions: list[Dimension] = field(default_factory=list)
review_trigger_rules: list[ReviewTriggerRule] = field(default_factory=list)
```

  `load_harness_config()` 从 `fitness.dimensions` 与 `review_triggers.rules` 填充它们。
- [ ] 运行 `python -m pytest tests/harness/test_config.py tests/test_review_trigger.py -q`，覆盖非法 enum、重复名称、空 rule 与省略段返回空列表。
- [ ] 提交：`feat(配置): 支持内联 Fitness 与审查规则`。

### 任务 2：使执行引擎只消费内联配置

**文件：** 修改 `entrix/engine.py`、`entrix/harness/engine.py`、`entrix/harness/producers/builtin.py`、`tests/harness/test_builtin_producers.py`、`tests/harness/test_engine.py`、`tests/test_engine.py`。

- [ ] 先写 `test_fitness_producer_uses_injected_dimensions`：在没有 `docs/fitness` 的临时目录加载 Harness，构造 `EntrixFitnessProducer(producer_config, config.fitness_dimensions)`，mock `run_fitness_report()`，断言 evidence 为 pass。
- [ ] 运行该测试；预期 producer 尚不接收 dimensions 而失败。
- [ ] 将 `run_fitness_report()` 改为 keyword-only `dimensions: list[Dimension]`，用 `filter_dimensions(dimensions, policy)` 替换 `load_dimensions(preset.fitness_dir(...))`。保留 preset 仅用于增量 domain 计算。
- [ ] `EvidenceEngine._create_producer()` 将 `self.config.fitness_dimensions` 或 `self.config.review_trigger_rules` 注入对应 builtin；review producer 直接把规则传给 `evaluate_review_triggers()`，删除 `docs/fitness/review-triggers.yaml` 拼接。
- [ ] 运行 `python -m pytest tests/harness/test_builtin_producers.py tests/harness/test_engine.py tests/test_engine.py -q`；预期临时项目不创建旧目录也通过。
- [ ] 提交：`refactor(执行): 从 Harness 配置读取质量规则`。

### 任务 3：默认模板、初始化与命令提示

**文件：** 创建 `entrix/harness/template.py`、`tests/harness/test_template.py`；修改 `entrix/cli.py`、`tests/test_cli.py`。

- [ ] 先写测试：首次 `entrix init --repo <tmp>` 创建 `.mcp.json` 与 `harness.yaml`；已有 `harness.yaml` 不加 `--force` 返回 1 且内容不变；`--force` 重建；根 `--help` 和 init stdout 包含 `harness validate`、`run`、`harness run`、`stop-gate`。
- [ ] 运行 `python -m pytest tests/test_cli.py tests/harness/test_template.py -q`；预期 `init` 当前只写 `.mcp.json` 而失败。
- [ ] 在模板模块用 `default_harness_config() -> dict[str, object]` 表示当前项目的 code_quality、testability、release_readiness、observability、performance 和 review trigger 默认规则。`render_default_harness()` 使用 `yaml.safe_dump(..., sort_keys=False, allow_unicode=True)`，且只留一个结尾换行。
- [ ] 为 init 添加 `--force`。成功时写模板并打印固定下一步导览：`entrix harness validate harness.yaml`、`entrix run`、`entrix harness run --json`、`entrix stop-gate`，每条附中文用途。根 `ArgumentParser` 用 `RawDescriptionHelpFormatter` 的中文 epilog 按任务列出 `init`、`run`、`harness validate/run`、`review-trigger`、`stop-gate`、`serve` 与最短示例。
- [ ] 运行上述测试；预期全部通过。
- [ ] 提交：`feat(初始化): 生成单文件 Harness 配置`。

### 任务 4：统一 CLI 与 Stop Hook 路由

**文件：** 修改 `entrix/cli.py`、`entrix/stop_gate/hook.py`、`entrix/stop_gate/runner.py`、`tests/test_harness_cli.py`、`tests/stop_gate/test_hook_cli.py`、`tests/stop_gate/test_harness_integration.py`。

- [ ] 先写测试：带有旧 `docs/fitness/` 但没有 `harness.yaml` 的 workspace 调用 Stop Hook 后无 stdout、返回 0；`entrix run` 在仅有 inline Harness 的临时目录运行；显式 `review-trigger` 使用 inline rules。
- [ ] 运行 `python -m pytest tests/test_harness_cli.py tests/stop_gate/test_hook_cli.py -q`；预期旧路径还会激活或 run 找不到 Fitness 目录而失败。
- [ ] 所有 `_find_fitness_dir()`/`_find_review_trigger_config()` 调用点改为加载当前 `harness.yaml` 并传入 `config.fitness_dimensions` 或 `config.review_trigger_rules`。缺少配置的显式质量命令向 stderr 输出“未找到 Harness 配置”并返回 1。
- [ ] 删除 `has_fitness_specs()` 与 `StopGateAdapter` legacy 回退。Hook 仅在找到 root 或 `.harness/harness.yaml` 时调用 `HarnessRunner`；两处都不存在时放行。
- [ ] 运行 `python -m pytest tests/test_harness_cli.py tests/stop_gate/test_hook_cli.py tests/stop_gate/test_harness_integration.py -q`；预期有 config 时使用 Harness、无 config 时放行、旧目录不参与决策。
- [ ] 提交：`refactor(门禁): 仅从 Harness 读取质量配置`。

### 任务 5：移除旧格式并迁移材料

**文件：** 删除 `entrix/loaders/evidence_loader.py` 和 `docs/fitness/` 全部文件；修改 `entrix/loaders/__init__.py`、`entrix/presets/base.py`、`entrix/presets/default.py`、`README.md`、`CONTRIBUTING.md`、`docs/stop-gate-usage.md`、`docs/adr/0002-harness-yaml-evidence-gate.md`；迁移 `examples/frontend-quality-pack/`、`tests/fixtures/skill_regression/`、`skills/entrix/` 及引用旧路径的测试。

- [ ] 先写 `test_load_harness_config_does_not_discover_docs_fitness`：临时项目即使存在 `docs/fitness`，调用不存在的 `harness.yaml` 仍抛出 `FileNotFoundError` 且消息含“Harness 配置”。
- [ ] 运行该单测，确认不存在任何回退发现行为后，删除 Markdown loader、manifest 发现和 `ProjectPreset.fitness_dir()`/`review_trigger_config()` 的调用及测试。
- [ ] 将 frontend example 与 skill-regression fixture 的质量配置改为根 `harness.yaml`；更新 README、贡献指南、ADR、使用文档和 `skills/entrix`，使示例只提单文件 schema。
- [ ] 运行 `rg -n "docs/fitness|review-triggers\.yaml|manifest\.yaml|load_dimensions" entrix tests examples README.md docs skills`；预期运行时代码、示例和测试没有旧路径，仅历史说明允许保留迁移文字。
- [ ] 运行 `python -m pytest tests/test_skill_regression_fixtures.py tests/test_structure_adapter.py -q`；预期通过。
- [ ] 提交：`refactor(配置): 移除多文件 Fitness 格式`。

### 任务 6：最终验收

**文件：** 仅修改最终验证发现问题所在的实现或测试文件。

- [ ] 运行 `python -m entrix.cli init --repo . --dry-run`，预期预览同时包含 `.mcp.json` 与 `harness.yaml`，且 Harness 预览有 `fitness`、`review_triggers`、`evidence_producers`、`gate_policies`。
- [ ] 运行 `python -m entrix.cli harness validate harness.yaml`，预期报告配置有效及各段数量。
- [ ] 运行 `python -m pytest tests -q`、`ruff check .`、`mypy`、`python -m build`，预期均以退出码 0 完成。
- [ ] 运行 `git diff --check` 与 `git diff main...HEAD --stat`，预期没有空白错误、虚拟环境、构建产物、运行时 evidence 或绝对路径。
- [ ] 提交：`test(配置): 验证单文件 Harness 工作流`。
- [ ] 向用户提供 `init`、根帮助、配置校验、Fitness 执行和一次 Claude Stop Hook 的手工检查清单；收到“测试通过”后才合并本地 `main` 并清理 worktree/分支。
