# Entrix 资源保护升级实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让 Harness 默认串行、为显式并行提供 YAML 和 CLI 双重上限，让 Fitness 的并行 worker 数可配置，并保证 `entrix init` 只初始化配置、不自动触发检查。

**架构：** Harness 配置定义 producer 并发硬上限，手工 CLI 显式请求并行后才会在该上限内启用线程池；Stop Hook 保持串行。Fitness CLI 将 `--max-workers` 传至 ShellRunner，但默认命令仍不并行。

**技术栈：** Python 3.11+、argparse、dataclasses、pytest、Ruff、Mypy。

**实施状态（2026-08-18）：** 任务 0 至任务 5 已完成并通过针对性回归、类型检查和配置校验。
任务 6 的全量 Ruff 仍被工作区中无关的 `tests/test_serialization_fix.py` 未使用导入阻断；本次
变更涉及文件的 Ruff 已通过。Java 多模块样例仓库的最终验收仍需在目标项目中执行。

---

## 文件职责

- `entrix/harness/config.py`：保存并验证 Harness 资源上限。
- `entrix/harness/engine.py`：根据配置和运行上下文限制 producer 并发。
- `entrix/cli.py`：解析并传递 Harness/Fitness 的并行参数。
- `entrix/cli_hints.py`：控制初始化后不自动提示执行检查。
- `skills/entrix/SKILL.md`：要求 Claude 在初始化后询问用户是否需要检查。
- `entrix/governance.py`：保存 Fitness worker 上限。
- `entrix/engine.py`：将 Fitness worker 上限传给 ShellRunner。
- `entrix/runners/shell.py`：使用调用方指定的 worker 上限。
- `entrix/harness/template.py`：生成保守的默认配置。
- `tests/harness/test_config.py`：验证资源配置 schema。
- `tests/harness/test_engine.py`：验证 producer 串行与受限并行。
- `tests/test_cli.py`：验证 CLI 参数和上下文传递。
- `tests/test_cli_hints.py`：验证初始化不会产生自动检查提示。
- `tests/test_engine.py`、`tests/test_shell_runner.py`：验证 Fitness worker 上限传递。
- `README.md`、`docs/stop-gate-usage.md`：说明 Java 的外层/内部并发限制。

### 任务 0：将初始化与检查解耦

**文件：**

- 修改：`tests/test_cli_hints.py`
- 修改：`entrix/cli_hints.py`
- 修改：`skills/entrix/SKILL.md`
- 修改：`README.md`

- [ ] **步骤 1：编写失败测试**

```python
def test_init_does_not_emit_automatic_check_hints() -> None:
    assert render_next_steps(("init",)) == ()
```

- [ ] **步骤 2：运行失败测试**

运行：

```powershell
python -m pytest tests/test_cli_hints.py -q
```

预期：当前 `("init",)` 映射包含 `entrix harness validate harness.yaml` 和 `entrix run`，因此新增测试失败。

- [ ] **步骤 3：最小实现与用户交互契约**

从 `NEXT_STEPS` 移除 `("init",)` 映射。保留 `cmd_init()` 的纯写入语义，不增加交互式 prompt。将 `/entrix` skill 的初始化后流程改为：展示已生成文件，询问「配置已生成。是否现在运行配置校验或本地检查？」；没有用户明确肯定答复时结束，不运行 `validate`、`run`、`harness run` 或 Stop Gate。README 将首次使用流程拆分为“初始化”和“经用户确认后运行检查”两个步骤。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/test_cli_hints.py -q
```

预期：退出码为 0。

### 任务 1：定义并验证 Harness 并发上限

**文件：**

- 修改：`tests/harness/test_config.py`
- 修改：`entrix/harness/config.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_loads_max_parallel_producers_from_settings(tmp_path: Path) -> None:
    config_path = _write_harness(tmp_path, settings={"failure_mode": "closed", "max_parallel_producers": 2})

    config = load_harness_config(config_path)

    assert config.max_parallel_producers == 2


@pytest.mark.parametrize("value", [0, -1, True, "2"])
def test_rejects_invalid_max_parallel_producers(tmp_path: Path, value: object) -> None:
    config_path = _write_harness(
        tmp_path,
        settings={"failure_mode": "closed", "max_parallel_producers": value},
    )

    with pytest.raises(ValueError, match="max_parallel_producers"):
        load_harness_config(config_path)
```

- [ ] **步骤 2：运行失败测试**

运行：

```powershell
python -m pytest tests/harness/test_config.py -q
```

预期：新增测试因 `HarnessConfig` 没有 `max_parallel_producers` 或未拒绝非法值而失败。

- [ ] **步骤 3：最小实现**

在 `HarnessConfig` 中增加 `max_parallel_producers: int = 1`。在 `load_harness_config()` 中读取 `settings.max_parallel_producers`，缺省为 1，并拒绝布尔值、非整数和小于 1 的值。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/harness/test_config.py -q
```

预期：退出码为 0。

### 任务 2：让 Harness 默认串行并受配置上限约束

**文件：**

- 修改：`tests/harness/test_engine.py`
- 修改：`entrix/harness/engine.py`

- [ ] **步骤 1：编写失败测试**

复用现有阻塞 producer helper，新增断言：默认 `HarnessRunContext` 同时活动的 producer 数为 1；`parallel_producers=True` 且 `max_parallel_producers=2` 时最多为 2；上下文请求 4 时仍被配置上限 2 限制。

```python
context = HarnessRunContext(
    task_id="manual-run",
    repo_root=tmp_path,
    when_context=WhenContext(repo_root=tmp_path),
    parallel_producers=True,
    max_parallel_producers=4,
)

bundle = engine.collect(context)

assert len(bundle.evidence) == 3
assert max_active == 2
```

- [ ] **步骤 2：运行失败测试**

运行：

```powershell
python -m pytest tests/harness/test_engine.py -q
```

预期：默认上下文仍并行或超过 2 个 producer 时失败。

- [ ] **步骤 3：最小实现**

将 `HarnessRunContext.parallel_producers` 默认改为 `False`，增加 `max_parallel_producers: int | None = None`。在 `EvidenceEngine.collect()` 计算有效 worker 数；只有有效值大于 1 时创建 `ThreadPoolExecutor(max_workers=effective_workers)`，否则保留顺序串行循环。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/harness/test_engine.py -q
```

预期：退出码为 0。

### 任务 3：公开 Harness CLI 的显式并行控制

**文件：**

- 修改：`tests/test_cli.py`
- 修改：`entrix/cli.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_harness_run_defaults_to_serial_collection(monkeypatch, tmp_path: Path) -> None:
    captured: list[HarnessRunContext] = []
    monkeypatch.setattr("entrix.cli.EvidenceEngine.collect", lambda _self, context: captured.append(context) or _bundle())

    assert run_cli(["harness", "run", "--config", str(_config(tmp_path))]) == 0
    assert captured[0].parallel_producers is False


def test_harness_run_caps_requested_workers(monkeypatch, tmp_path: Path) -> None:
    # Configure max_parallel_producers: 2, request 4, and assert context requests 4.
    # EvidenceEngine is responsible for applying the final cap.
    assert run_cli(["harness", "run", "--parallel", "--max-workers", "4", "--config", str(_config(tmp_path))]) == 0
```

- [ ] **步骤 2：运行失败测试**

运行：

```powershell
python -m pytest tests/test_cli.py -q
```

预期：CLI 不认识 `--parallel` 或默认上下文为并行时失败。

- [ ] **步骤 3：最小实现**

给 `harness run` 增加 `--parallel` 和 `--max-workers`。`--max-workers` 使用正整数 validator，并只在 `--parallel` 为真时传入 `HarnessRunContext`。没有 `--parallel` 时上下文明确传入 `False`。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/test_cli.py -q
```

预期：退出码为 0。

### 任务 4：让 Fitness 并发 worker 数可配置

**文件：**

- 修改：`tests/test_cli.py`
- 修改：`tests/test_engine.py`
- 修改：`tests/test_shell_runner.py`
- 修改：`entrix/governance.py`
- 修改：`entrix/engine.py`
- 修改：`entrix/runners/shell.py`
- 修改：`entrix/cli.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_run_cli_passes_max_workers_to_policy(monkeypatch) -> None:
    captured: list[GovernancePolicy] = []
    monkeypatch.setattr("entrix.cli.run_fitness_report", lambda *_args, **kwargs: _report_and_dimensions())

    assert run_cli(["run", "--parallel", "--max-workers", "2"]) == 0
    assert captured[0].parallel is True
    assert captured[0].max_workers == 2
```

在 `tests/test_engine.py` 使用记录 `run_batch()` 参数的 fake `ShellRunner`，断言 `max_workers=2` 被传入；在 `tests/test_shell_runner.py` 断言 `parallel=False` 时不创建 executor，`parallel=True` 时 executor 使用指定上限。

- [ ] **步骤 2：运行失败测试**

运行：

```powershell
python -m pytest tests/test_cli.py tests/test_engine.py tests/test_shell_runner.py -q
```

预期：CLI 不认识 `--max-workers` 或 worker 数未传递时失败。

- [ ] **步骤 3：最小实现**

在 `GovernancePolicy` 增加 `max_workers: int = 4`，在 CLI 增加正整数 `--max-workers`（默认 4），将其传给 `_run_metric_batch()` 和 `ShellRunner.run_batch()`。保持没有 `--parallel` 时的串行逻辑。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/test_cli.py tests/test_engine.py tests/test_shell_runner.py -q
```

预期：退出码为 0。

### 任务 5：更新默认模板和使用文档

**文件：**

- 修改：`entrix/harness/template.py`
- 修改：`tests/harness/test_template.py`
- 修改：`README.md`
- 修改：`docs/stop-gate-usage.md`

- [ ] **步骤 1：编写失败测试**

```python
def test_default_harness_template_limits_producer_parallelism() -> None:
    config = default_harness_config()

    assert config["settings"]["max_parallel_producers"] == 1
```

- [ ] **步骤 2：运行失败测试**

运行：

```powershell
python -m pytest tests/harness/test_template.py -q
```

预期：默认模板缺少该字段时失败。

- [ ] **步骤 3：最小实现与文档**

在默认 `settings` 写入 `max_parallel_producers: 1`。在 README 和 Stop Gate 指南说明：默认串行、手工 Harness 的显式并行参数、配置上限优先，以及 Maven/Surefire/Gradle 的外层与内部并发示例。README 保持初始化与检查分离：`entrix init` 只生成配置，检查仅在用户明确确认后运行。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/harness/test_template.py -q
```

预期：退出码为 0。

### 任务 6：完整验证

**文件：** 无新增文件。

- [ ] **步骤 1：运行受影响测试集**

```powershell
python -m pytest tests/harness/test_config.py tests/harness/test_engine.py tests/harness/test_template.py tests/test_cli.py tests/test_engine.py tests/test_shell_runner.py -q
```

预期：退出码为 0。

- [ ] **步骤 2：运行静态检查与配置验证**

```powershell
ruff check entrix tests
mypy entrix/harness/config.py entrix/harness/engine.py entrix/governance.py entrix/engine.py entrix/runners/shell.py
python -m entrix harness validate harness.yaml
python -m entrix harness run --help
python -m entrix run --help
```

预期：所有命令退出码为 0，两个 help 都显示新的 worker 参数。

- [ ] **步骤 3：提交与用户验证**

在独立分支提交后，请用户在 Java 多模块样例仓库验证：

```powershell
entrix run --tier fast --dry-run
entrix harness run --config harness.yaml --json
```

验收时观察 Maven 命令没有由 Entrix 并行启动；再验证 `-T1`、Surefire `forkCount=1` 或 Gradle `--max-workers=1` 将 JVM 数量保持在项目可承受范围内。
