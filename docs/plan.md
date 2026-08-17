# Entrix Harness/Stop Gate 修复实施计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复审查中发现的 Harness 配置裁决、Stop hook 路由、内置 producer、DSL 和测试基线问题。

**架构：** 无 `harness.yaml` 时保留 legacy Stop Gate；存在配置时由 hook 直接运行 HarnessRunner。YAML 在加载边界转换为 `GatePolicy` 等领域对象，producer 通过现有 `engine`/`review_trigger` API 生成标准 evidence。

**技术栈：** Python 3.10+, dataclasses, PyYAML, pytest, Ruff, mypy, Hatchling。

---

## 文件清单

- 修改：`entrix/harness/config.py`，配置校验与领域模型转换。
- 修改：`entrix/harness/engine.py`、`entrix/harness/gate/arbiter.py`，明确 typed policy 输入和错误语义。
- 修改：`entrix/harness/producers/builtin.py`，适配现有 Entrix API。
- 修改：`entrix/harness/gate/dsl.py`，实现列表、`int` 和尾部 token 校验。
- 修改：`entrix/stop_gate/hook.py`、`entrix/stop_gate/runner.py`、`entrix/stop_gate/adapter.py`，实现配置路由并消除 Harness 对 legacy adapter 的依赖。
- 修改：`entrix/cli.py`，使用转换后的 policy，并修正 harness 命令错误出口。
- 修改：`tests/harness/`、`tests/stop_gate/`，新增回归测试、唯一模块收集和跨平台临时目录。
- 修改：`pyproject.toml`，pytest 收集模式、Ruff/Mypy 最小配置。
- 修改：`.gitignore`，忽略本地 evidence 运行产物。
- 不修改：`entrix/cli.py` 的整体命令拆分；本计划只改 harness 相关调用点。

## 任务 1：建立可运行的测试基线

**目标：** 让默认测试命令能收集并准确暴露现有失败。

- [ ] 重命名 `tests/harness/test_engine.py` 与 `tests/stop_gate/test_engine.py` 等重复 basename，或在 `pyproject.toml` 设置 `--import-mode=importlib`，并选择一种全仓统一方案。
- [ ] 将 harness 测试中写死的 `/tmp` 改成 `tmp_path` fixture；将 `sleep 10` 改成 `sys.executable -c` 的跨平台短等待。
- [ ] 运行 `python -m pytest --collect-only`，预期完成收集且无 import mismatch。
- [ ] 提交：`test: stabilize cross-platform harness test baseline`。

## 任务 2：修复配置到领域模型的边界

**目标：** `HarnessConfig` 输出只能被 `GateEngine` 正确消费。

- [ ] 先在 `tests/harness/test_config.py` 增加：severity 转枚举、rule 转 `GateRule`、重复 producer id、缺少 evidence selector、未知 builtin 和无 pattern regex 的失败测试；运行对应测试确认失败。
- [ ] 在 `entrix/harness/config.py` 增加明确的 `to_domain()`/构造转换，校验 producer/gate 必填字段和枚举值；不把原始 dict 传出配置层。
- [ ] 在 `entrix/cli.py` 和 `entrix/stop_gate/runner.py` 使用转换后的 `GatePolicy` 列表；修复缺 evidence 时对 raw dict 的访问。
- [ ] 运行 `python -m pytest tests/harness/test_config.py tests/harness/test_arbiter.py -v`，预期全部通过。
- [ ] 提交：`fix: normalize harness policies before arbitration`。

## 任务 3：修复 Gate DSL 和 producer

**目标：** 配置文档声明的表达式和内置 producer 真正可用。

- [ ] 先在 `tests/harness/test_gate_dsl.py` 增加列表 membership、`int(summary.failed)`、尾部垃圾 token 和除零/未知字段测试；运行确认失败。
- [ ] 在 `entrix/harness/gate/dsl.py` 实现列表字面量、白名单 `int`、完整 token 消费和清晰异常；禁止动态 Python 求值。
- [ ] 在 `tests/harness/test_builtin_producers.py` 增加对实际 `entrix.engine.run_fitness_report` 和 `entrix.review_trigger` API 的 mock 契约测试，断言 summary/status 结构。
- [ ] 在 `entrix/harness/producers/builtin.py` 改用实际模块和签名，保留异常为 evidence error 的行为。
- [ ] 运行 `python -m pytest tests/harness/test_gate_dsl.py tests/harness/test_builtin_producers.py -v`，预期全部通过。
- [ ] 提交：`fix: align harness DSL and builtin producers`。

## 任务 4：接通 Stop hook 路由

**目标：** 有 harness 配置时不再走旧 collector/arbiter，无配置时兼容旧行为。

- [ ] 先在 `tests/stop_gate/test_hook_cli.py` 增加路由测试：root `harness.yaml`、`.harness/harness.yaml`、无配置三种情况；mock runner/legacy adapter，运行确认失败。
- [ ] 在 `entrix/stop_gate/hook.py` 增加配置定位和 HarnessRunner 分支，保持 stdin/stdout/exit code hook 契约。
- [ ] 在 `entrix/stop_gate/runner.py` 直接构造 `HarnessRunContext`，删除对 `StopGateAdapter` 的初始化依赖，并把 verdict 转成 hook 可用反馈。
- [ ] 确保 Harness 路径异常阻断，legacy 路径行为不变。
- [ ] 运行 `python -m pytest tests/stop_gate/test_hook_cli.py tests/stop_gate/test_harness_integration.py tests/stop_gate/test_integration.py -v`，预期通过。
- [ ] 提交：`fix: route stop hook through configured harness`。

## 任务 5：配置工程基线与文档契约

**目标：** 将质量门槛写入项目工具配置，避免问题再次回归。

- [ ] 在 `pyproject.toml` 增加 pytest import mode、Ruff 选择规则和与当前 Python 版本兼容的 mypy 配置；不改变业务运行时行为。
- [ ] 在 `.gitignore` 增加 `.harness/evidence/`，避免执行 hook 污染工作树。
- [ ] 运行 `ruff check .`，修复本次触及文件中的 lint 错误；再运行 `python -m pytest`。
- [ ] 运行 `python -m build`，确认 wheel/sdist 可构建。
- [ ] 提交：`chore: enforce harness quality gates`。

## 任务 6：最终验收与合并前检查

- [ ] 在隔离分支执行完整 `python -m pytest`、`ruff check .`、`python -m build`，记录退出码和统计。
- [ ] 运行最小 CLI smoke test：有效 hard gate、失败 hard gate、blocked gate、无配置 legacy fallback。
- [ ] 检查 `git diff main...HEAD`，确认没有临时 evidence、绝对路径或无关重构。
- [ ] 提交最终修正后，等待用户确认测试结果，再合并到本地 `main`。
- [ ] 合并后在 `main` 重跑完整验证，随后移除 worktree、执行 `git worktree prune` 并删除修复分支。

## 验收命令

```powershell
python -m pytest
ruff check .
python -m build
python -m entrix.cli harness validate harness.yaml
```

在没有真实 `harness.yaml` 的仓库中，CLI smoke test 使用临时目录生成最小配置，不在仓库中留下 evidence。

---

# Harness DoD 强门禁实施计划（2026-08-17）

**目标：** 在现有 Harness 主链路上实现 fail-closed、三级条件、六种标准解析器、严格 Evidence Store、Gate 仲裁和 PASS 强制重验。

**里程碑与预估：** 配置与证据基础 2.5 小时；标准报告解析 4 小时；收集与仲裁 2.5 小时；Stop Hook 强化 2 小时；CLI 子命令提示 1.5 小时；集成、文档与验证 1.5 小时，合计 14 小时。

**详细计划：** `docs/superpowers/plans/2026-08-17-harness-dod-hardening.md`。

**测试策略：** 11 个任务均先写失败测试并确认 RED，再写最小实现并确认 GREEN；最终执行全量 pytest、Ruff、Mypy、Harness 配置校验、package build 和真实 Claude Code 手动验收。

---

# Entrix 单文件 Harness 配置实施计划

**目标：** 用 `harness.yaml` 取代 Fitness Markdown、manifest 与 review trigger 文件，并由 `entrix init` 生成默认配置。

**里程碑与预估：** 领域配置和执行迁移约 3 小时；初始化、帮助与 Hook 路由约 2 小时；旧格式、示例和文档迁移约 3 小时；全量验证与用户测试约 1 小时。

**详细计划：** `docs/superpowers/plans/2026-08-17-unified-harness-configuration.md`。

**测试策略：** 每个阶段先添加失败测试；覆盖内联 YAML 解析、初始化覆盖保护、命令帮助、Fitness/Review 执行、Stop Hook 与无旧目录依赖。最终执行 pytest、Ruff、Mypy 和构建。
