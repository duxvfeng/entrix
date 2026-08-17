# Harness DoD 强门禁实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将现有 Claude Stop Harness 强化为默认拒绝、三级条件激活、标准报告解析、证据原子持久化且每次 PASS 都重新验证的 DoD 门禁。

**架构：** 保留 `HarnessRunner -> EvidenceEngine -> EvidenceStore -> GateEngine` 主链路，在 Harness 内新增受控 Parser Registry。Stop Hook 只负责生命周期、缓存和 fail-closed；Gate Engine 只消费标准 Evidence 与 WhenContext。

**技术栈：** Python 3.10+、dataclasses、PyYAML、ElementTree、pytest、Ruff、Mypy、Hatchling。

---

## 文件结构

### 新建

- `entrix/harness/parsers/__init__.py`：受控 parser 注册表和统一分派入口。
- `entrix/harness/parsers/base.py`：ParserContext、ParserResult、报告/artifact 安全路径解析。
- `entrix/harness/parsers/process.py`：`exit_code` 与 `regex` 解析器。
- `entrix/harness/parsers/junit.py`：JUnit XML 聚合解析。
- `entrix/harness/parsers/json_report.py`：通用 JSON 点路径映射。
- `entrix/harness/parsers/sarif.py`：SARIF 2.x 聚合解析。
- `entrix/harness/parsers/evidence_json.py`：标准 `evidence/v1` 输入校验与规范化。
- `entrix/cli_hints.py`：子命令纠错、命令组帮助和下一步提示策略。
- `tests/harness/test_parser_process.py`：进程结果 parser 测试。
- `tests/harness/test_parser_junit.py`：JUnit 报告测试。
- `tests/harness/test_parser_json.py`：通用 JSON 与 evidence JSON 测试。
- `tests/harness/test_parser_sarif.py`：SARIF 报告测试。
- `tests/test_cli_hints.py`：CLI 提示算法与输出隔离测试。

### 修改

- `entrix/harness/config.py`：settings、三级 when、parser/artifact、非空配置校验。
- `entrix/harness/conditions.py`：glob、ANY/AND、路径安全和配置类型校验。
- `entrix/harness/evidence.py`：合法状态、bundle revision/fingerprint/active 元数据。
- `entrix/harness/store.py`：原子保存和严格失败语义。
- `entrix/harness/producers/command.py`：只执行命令并委托 Parser Registry。
- `entrix/harness/producers/builtin.py`：补齐 duration、artifact 和标准错误字段。
- `entrix/harness/engine.py`：skipped Evidence、inactive bundle、严格存储。
- `entrix/harness/gate/policy.py`：GatePolicy `when`。
- `entrix/harness/gate/arbiter.py`：Gate 条件、missing evidence、zero active gates、blocked ANY 语义。
- `entrix/stop_gate/runner.py`：传递 WhenContext 和严格 Evidence Store。
- `entrix/stop_gate/hook.py`：fail-closed、PASS 重跑、FAIL/BLOCKED 缓存和指纹修复。
- `entrix/stop_gate/revalidation.py`：缓存只保存非 PASS 裁决。
- `hooks/stop-gate.sh`：运行器缺失时输出 block JSON。
- `entrix/cli.py`：接入统一提示 parser、命令路径和成功提示。
- `tests/test_cli.py`：根/嵌套命令解析与提示集成测试。
- `tests/harness/test_config.py`、`test_conditions.py`、`test_engine.py`、`test_store.py`、`test_arbiter.py`：核心回归测试。
- `tests/stop_gate/test_hook_cli.py`、`test_harness_integration.py`：Hook 和闭环测试。
- `harness.yaml`、`entrix/harness/template.py`：显式 strict settings 和当前格式示例。
- `README.md`、`docs/stop-gate-usage.md`：fail-closed、parser、紧急旁路说明。

## 里程碑与预估

| 里程碑 | 任务 | 预计工时 |
| --- | --- | ---: |
| 配置与证据基础 | 1-2 | 2.5h |
| 标准报告解析 | 3-6 | 4h |
| 收集与仲裁闭环 | 7-8 | 2.5h |
| Stop Hook 强化 | 9 | 2h |
| CLI 子命令提示 | 10 | 1.5h |
| 集成、文档与验证 | 11 | 1.5h |
| 合计 |  | 14h |

## 任务 1：收紧配置与条件契约

**文件：**

- 修改：`entrix/harness/config.py`
- 修改：`entrix/harness/conditions.py`
- 修改：`entrix/harness/gate/policy.py`
- 测试：`tests/harness/test_config.py`
- 测试：`tests/harness/test_conditions.py`

- [ ] **步骤 1：添加失败的配置测试**

在 `tests/harness/test_config.py` 增加完整配置用例，断言 settings 和 Gate `when` 被转换，并用参数化用例拒绝空 producer、空 Gate、`failure_mode: open`、未知 when 谓词和非法 parser 字段：

```python
def test_loads_closed_settings_and_gate_when(tmp_path: Path) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text(
        '''version: "harness/v1"
settings: {failure_mode: closed}
evidence_producers:
  - id: tests
    type: test
    name: Tests
    command: pytest
gate_policies:
  - name: Tests pass
    severity: hard
    when: {changed_any: ["src/**"]}
    rule: {evidence_id: tests, condition: 'status == "pass"'}
''',
        encoding="utf-8",
    )

    config = load_harness_config(config_path)

    assert config.failure_mode == "closed"
    assert config.gate_policies[0].when == {"changed_any": ["src/**"]}
```

- [ ] **步骤 2：运行配置测试并确认 RED**

运行：

```powershell
python -m pytest tests/harness/test_config.py -q
```

预期：新增用例因 `failure_mode`/`GatePolicy.when` 不存在或空列表仍被接受而失败。

- [ ] **步骤 3：添加失败的条件语义与路径测试**

在 `tests/harness/test_conditions.py` 增加：`files_exist` glob 任一命中、多个谓词 AND、绝对路径拒绝、`..` 逃逸拒绝、未知谓词抛配置错误：

```python
def test_files_exist_supports_glob_with_any_semantics(tmp_path: Path) -> None:
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    context = WhenContext(repo_root=tmp_path)

    assert evaluate_when(
        {"files_exist": ["missing.lock", "frontend/*.json"]}, context
    ) is True


@pytest.mark.parametrize("pattern", ["../outside.txt", str(Path.cwd().anchor)])
def test_files_exist_rejects_paths_outside_workspace(tmp_path: Path, pattern: str) -> None:
    with pytest.raises(ValueError, match="工作区"):
        evaluate_when({"files_exist": [pattern]}, WhenContext(repo_root=tmp_path))
```

- [ ] **步骤 4：运行条件测试并确认 RED**

运行：

```powershell
python -m pytest tests/harness/test_conditions.py -q
```

预期：glob 用例返回 False，路径逃逸用例未抛错。

- [ ] **步骤 5：实现最小配置与条件模型**

在 `GatePolicy` 增加 `when: dict[str, object] | None`；在 `HarnessConfig` 增加默认 `failure_mode="closed"`。加载时调用 `validate_when_config()`，并把 producer/Gate 非空要求放在 YAML 加载边界。条件模块使用 `Path.glob` 和 `Path.resolve()`，拒绝不在 `repo_root.resolve()` 下的候选路径。

核心接口固定为：

```python
def validate_when_config(when: object, field_name: str) -> dict[str, object] | None:
    """Validate and normalize one declarative activation block."""


def evaluate_when(when: dict[str, object] | None, context: WhenContext) -> bool:
    """Evaluate normalized predicates with AND-between/ANY-within semantics."""
```

- [ ] **步骤 6：验证 GREEN 并提交**

运行：

```powershell
python -m pytest tests/harness/test_config.py tests/harness/test_conditions.py -q
ruff check entrix/harness/config.py entrix/harness/conditions.py entrix/harness/gate/policy.py
```

预期：全部通过。提交：`feat(配置): 收紧 Harness 条件与门禁配置`。

## 任务 2：完善 Evidence Bundle 与原子存储

**文件：**

- 修改：`entrix/harness/evidence.py`
- 修改：`entrix/harness/store.py`
- 测试：`tests/harness/test_evidence.py`
- 测试：`tests/harness/test_store.py`

- [ ] **步骤 1：添加失败的模型与原子写入测试**

覆盖非法 Evidence 状态、bundle 自动 `collected_at`、revision/fingerprint/active 字段，以及 `Path.replace()` 失败时目标文件不存在：

```python
def test_evidence_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="status"):
        Evidence(id="tests", status="unknown")


def test_store_does_not_leave_partial_bundle_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = EvidenceStore(tmp_path)
    monkeypatch.setattr(Path, "replace", lambda *_args: (_ for _ in ()).throw(OSError("disk")))

    with pytest.raises(OSError, match="disk"):
        store.save(EvidenceBundle(task_id="task", attempt_id="attempt"))

    assert not list((tmp_path / ".harness" / "evidence").rglob("*-bundle.json"))
```

- [ ] **步骤 2：运行测试并确认 RED**

运行：`python -m pytest tests/harness/test_evidence.py tests/harness/test_store.py -q`

预期：非法状态未拒绝、时间字段为空或 store 直接写目标文件。

- [ ] **步骤 3：实现模型校验和原子保存**

`Evidence.__post_init__()` 校验非空状态时属于允许集合。`EvidenceBundle` 使用 UTC 工厂填充 `collected_at`，增加 `active`、`revision`、`workspace_fingerprint`。Store 在 task 目录内创建唯一 `.tmp` 文件，`flush()`、`os.fsync()` 后 `Path.replace()`，异常时清理临时文件并重新抛出。

- [ ] **步骤 4：验证 GREEN 并提交**

运行：`python -m pytest tests/harness/test_evidence.py tests/harness/test_store.py -q`

预期：全部通过且 task 目录无 `.tmp` 残留。提交：`feat(证据): 原子保存标准 Evidence Bundle`。

## 任务 3：建立 Parser Registry 与进程解析器

**文件：**

- 新建：`entrix/harness/parsers/__init__.py`
- 新建：`entrix/harness/parsers/base.py`
- 新建：`entrix/harness/parsers/process.py`
- 修改：`entrix/harness/producers/command.py`
- 新建：`tests/harness/test_parser_process.py`
- 修改：`tests/harness/test_command_producer.py`

- [ ] **步骤 1：添加失败的注册表和 artifact 安全测试**

在 `tests/harness/test_parser_process.py` 定义本文件使用的完整 helper：

```python
def parse_with(
    parser_type: str,
    repo_root: Path,
    config: dict[str, object],
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> ParserResult:
    process = subprocess.CompletedProcess(
        args="test-command",
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
    context = ParserContext(
        repo_root=repo_root,
        config=config,
        completed_process=process,
    )
    return get_parser(parser_type).parse(context)
```

```python
def test_registry_rejects_unknown_parser() -> None:
    with pytest.raises(ValueError, match="parser"):
        get_parser("python_eval")


def test_resolve_workspace_file_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="工作区"):
        resolve_workspace_file(tmp_path, "../report.xml")
```

同时把现有 exit-code/regex 测试迁移到统一 `parse_result()` 入口，断言命名组数字保持数值类型。

- [ ] **步骤 2：运行 parser 测试并确认 RED**

运行：`python -m pytest tests/harness/test_parser_process.py -q`

预期：模块不存在。

- [ ] **步骤 3：实现稳定 parser 接口**

```python
@dataclass(frozen=True)
class ParserContext:
    repo_root: Path
    config: dict[str, object]
    completed_process: subprocess.CompletedProcess[str]


@dataclass
class ParserResult:
    status: str
    summary: dict[str, object] = field(default_factory=dict)
    raw: dict[str, object] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)


class EvidenceParser(Protocol):
    def parse(self, context: ParserContext) -> ParserResult: ...
```

注册表只包含固定 key。`CommandProducer` 保留超时与进程树终止逻辑，完成后把 `CompletedProcess` 交给 parser，再把 ParserResult 合并到 Evidence。

- [ ] **步骤 4：接入声明式 artifact**

对 `config.artifacts` 逐项调用安全路径解析并检查普通文件；规范化为 POSIX 相对路径。不存在或越界时把 Evidence 置为 `error`，在 `raw.error` 记录原因。

- [ ] **步骤 5：验证 GREEN 并提交**

运行：

```powershell
python -m pytest tests/harness/test_parser_process.py tests/harness/test_command_producer.py -q
ruff check entrix/harness/parsers entrix/harness/producers/command.py
```

提交：`refactor(证据): 引入受控 Parser Registry`。

## 任务 4：实现 JUnit XML parser

**文件：**

- 新建：`entrix/harness/parsers/junit.py`
- 修改：`entrix/harness/parsers/__init__.py`
- 新建：`tests/harness/test_parser_junit.py`
- 修改：`tests/harness/test_config.py`

- [ ] **步骤 1：添加 JUnit RED 测试**

用 `tmp_path` 写入 testsuites、多 suite、failure/error、缺失文件、损坏 XML 和越界路径六类报告。核心成功断言：

```python
def parse_with(parser_type: str, repo_root: Path, config: dict[str, object]) -> ParserResult:
    process = subprocess.CompletedProcess("test-command", 0, "", "")
    context = ParserContext(repo_root, config, process)
    return get_parser(parser_type).parse(context)


def test_junit_aggregates_nested_suites(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="1" time="1.5" />'
        '<testsuite tests="2" failures="0" errors="0" skipped="0" time="0.5" /></testsuites>',
        encoding="utf-8",
    )

    result = parse_with("junit", tmp_path, {"path": "junit.xml"})

    assert result.status == "fail"
    assert result.summary == {
        "total": 5,
        "passed": 3,
        "failed": 1,
        "errors": 0,
        "skipped": 1,
        "duration_seconds": 2.0,
    }
```

- [ ] **步骤 2：运行并确认 RED**

运行：`python -m pytest tests/harness/test_parser_junit.py tests/harness/test_config.py -q`

预期：`junit` 未注册或配置校验拒绝。

- [ ] **步骤 3：实现安全聚合解析**

使用 `xml.etree.ElementTree.parse()`，统一处理根节点 `testsuite`/`testsuites`，以属性聚合为准；不存在的数值视为 0，非法数值产生 `error` ParserResult，不读取外部路径。

- [ ] **步骤 4：验证 GREEN 并提交**

运行：`python -m pytest tests/harness/test_parser_junit.py tests/harness/test_config.py -q`

提交：`feat(证据): 支持 JUnit XML 报告解析`。

## 任务 5：实现通用 JSON 与 evidence_json parser

**文件：**

- 新建：`entrix/harness/parsers/json_report.py`
- 新建：`entrix/harness/parsers/evidence_json.py`
- 修改：`entrix/harness/parsers/__init__.py`
- 新建：`tests/harness/test_parser_json.py`
- 修改：`tests/harness/test_config.py`

- [ ] **步骤 1：添加 JSON 映射 RED 测试**

覆盖 dict/list 点路径、status_map、summary 数字、缺失路径、损坏 JSON、非对象根节点：

```python
def parse_with(parser_type: str, repo_root: Path, config: dict[str, object]) -> ParserResult:
    process = subprocess.CompletedProcess("test-command", 0, "", "")
    context = ParserContext(repo_root, config, process)
    return get_parser(parser_type).parse(context)


def test_json_parser_maps_status_and_summary(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text(
        '{"result":{"status":"success"},"stats":{"total":4,"failed":0}}',
        encoding="utf-8",
    )
    config = {
        "path": "result.json",
        "status_path": "result.status",
        "status_map": {"success": "pass", "failed": "fail"},
        "summary": {"total": "stats.total", "failed": "stats.failed"},
    }

    result = parse_with("json", tmp_path, config)

    assert result.status == "pass"
    assert result.summary == {"total": 4, "failed": 0}
```

- [ ] **步骤 2：添加 evidence_json 身份覆盖 RED 测试**

输入伪造 `id/task_id/started_at`，断言 parser 只返回可接受的 status/summary/raw/artifacts，最终 Evidence 身份仍来自 Harness config/context。

- [ ] **步骤 3：运行并确认 RED**

运行：`python -m pytest tests/harness/test_parser_json.py -q`

预期：模块或 parser key 不存在。

- [ ] **步骤 4：实现只读点路径映射与 schema 校验**

`read_path(data, "runs.0.status")` 只遍历 dict key 和数字 list index。`evidence_json` 要求 `schema_version == "evidence/v1"`、合法 status、对象 summary/raw 和 artifact 列表，不执行表达式。

- [ ] **步骤 5：验证 GREEN 并提交**

运行：`python -m pytest tests/harness/test_parser_json.py tests/harness/test_command_producer.py -q`

提交：`feat(证据): 支持 JSON 与标准 Evidence 输入`。

## 任务 6：实现 SARIF parser

**文件：**

- 新建：`entrix/harness/parsers/sarif.py`
- 修改：`entrix/harness/parsers/__init__.py`
- 新建：`tests/harness/test_parser_sarif.py`
- 修改：`tests/harness/test_config.py`

- [ ] **步骤 1：添加 SARIF RED 测试**

覆盖空 runs、多 runs、error/warning/note、缺失 level、阻断级别配置和损坏结构：

```python
def parse_with(parser_type: str, repo_root: Path, config: dict[str, object]) -> ParserResult:
    process = subprocess.CompletedProcess("test-command", 0, "", "")
    context = ParserContext(repo_root, config, process)
    return get_parser(parser_type).parse(context)


def write_sarif(path: Path, levels: list[str]) -> None:
    payload = {
        "version": "2.1.0",
        "runs": [
            {
                "results": [
                    {"ruleId": f"rule-{index}", "level": level}
                    for index, level in enumerate(levels)
                ]
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_sarif_fails_when_configured_blocking_level_is_present(tmp_path: Path) -> None:
    write_sarif(tmp_path / "scan.sarif", levels=["warning", "error", "note"])

    result = parse_with(
        "sarif",
        tmp_path,
        {"path": "scan.sarif", "blocking_levels": ["error"]},
    )

    assert result.status == "fail"
    assert result.summary["results"] == 3
    assert result.summary["errors"] == 1
```

- [ ] **步骤 2：运行并确认 RED**

运行：`python -m pytest tests/harness/test_parser_sarif.py -q`

预期：`sarif` 未注册。

- [ ] **步骤 3：实现 SARIF 聚合**

校验根对象与 `runs` 列表；聚合 results、levels、ruleId 唯一数。默认 `blocking_levels=["error"]`，配置只允许 `error/warning/note/none`。

- [ ] **步骤 4：验证 GREEN 并提交**

运行：`python -m pytest tests/harness/test_parser_sarif.py tests/harness/test_config.py -q`

提交：`feat(证据): 支持 SARIF 扫描报告解析`。

## 任务 7：实现 skipped Evidence 与严格收集存储

**文件：**

- 修改：`entrix/harness/engine.py`
- 修改：`entrix/harness/producers/builtin.py`
- 修改：`entrix/stop_gate/runner.py`
- 测试：`tests/harness/test_engine.py`
- 测试：`tests/harness/test_builtin_producers.py`
- 测试：`tests/stop_gate/test_harness_integration.py`

- [ ] **步骤 1：添加 producer skipped 和 inactive bundle RED 测试**

```python
def test_inactive_producer_emits_skipped_evidence(tmp_path: Path) -> None:
    producer = EvidenceProducerConfig(
        id="tests",
        type="test",
        name="Tests",
        command="pytest",
        when={"changed_any": ["frontend/**"]},
    )
    policy = GatePolicy(
        name="Tests pass",
        severity=Severity.HARD,
        rule=GateRule(evidence_id="tests", condition='status == "pass"'),
    )
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[producer],
        gate_policies=[policy],
    )
    context = HarnessRunContext(
        task_id="task",
        repo_root=tmp_path,
        when_context=WhenContext(
            repo_root=tmp_path,
            changed_files=["docs/readme.md"],
            current_branch="main",
        ),
    )

    bundle = EvidenceEngine(config).collect(context)

    assert [(item.id, item.status) for item in bundle.evidence] == [("tests", "skipped")]
```

顶层 inactive 用例断言 `bundle.active is False`、bundle 被 Store 保存且不运行 producer。

- [ ] **步骤 2：添加存储失败 RED 测试**

注入 `EvidenceStore.save()` 抛 `OSError`，断言 `EvidenceEngine.collect()` 重新抛出，HarnessRunner 不调用 GateEngine。

- [ ] **步骤 3：运行并确认 RED**

运行：`python -m pytest tests/harness/test_engine.py tests/stop_gate/test_harness_integration.py -q`

- [ ] **步骤 4：实现最小收集语义**

为每个未激活 producer 创建带身份、时间和 `raw.reason="when condition not met"` 的 skipped Evidence。顶层 inactive 构造并保存 inactive bundle。Store 异常不吞掉。Builtin producer 使用 monotonic 计时补齐 duration。

- [ ] **步骤 5：验证 GREEN 并提交**

运行：

```powershell
python -m pytest tests/harness/test_engine.py tests/harness/test_builtin_producers.py tests/stop_gate/test_harness_integration.py -q
```

提交：`feat(证据): 保存 skipped 与 inactive 收集事实`。

## 任务 8：实现 Gate 条件和严格仲裁

**文件：**

- 修改：`entrix/harness/gate/arbiter.py`
- 修改：`entrix/stop_gate/runner.py`
- 测试：`tests/harness/test_arbiter.py`
- 测试：`tests/stop_gate/test_harness_integration.py`

- [ ] **步骤 1：添加 Gate 仲裁 RED 测试**

覆盖 Gate when inactive、hard 对所有匹配 Evidence、blocked 任一触发、missing evidence BLOCKED、zero active gates BLOCKED：

```python
def test_blocked_gate_triggers_when_any_matching_evidence_matches() -> None:
    bundle = EvidenceBundle(
        evidence=[
            Evidence(id="a", type="scan", status="pass"),
            Evidence(id="b", type="scan", status="fail"),
        ]
    )
    policy = GatePolicy(
        name="No failed scan",
        severity=Severity.BLOCKED,
        rule=GateRule(evidence_type="scan", condition='status == "fail"'),
    )

    verdict = GateEngine([policy]).arbitrate(bundle, WhenContext())

    assert verdict.status == VerdictStatus.BLOCKED
```

- [ ] **步骤 2：运行并确认 RED**

运行：`python -m pytest tests/harness/test_arbiter.py -q`

预期：新签名、inactive 和 ANY 语义失败。

- [ ] **步骤 3：实现仲裁状态机**

`GateEngine.arbitrate(bundle, when_context)` 先过滤 Gate。GateResult 增加 `active`。missing evidence 返回不通过，最终状态为 BLOCKED；hard 失败为 FAIL；blocked 任一条件 True 为 BLOCKED；soft/advisory 只记录。状态优先级为 `BLOCKED > FAIL > PASS`。

- [ ] **步骤 4：验证 GREEN 并提交**

运行：`python -m pytest tests/harness/test_arbiter.py tests/stop_gate/test_harness_integration.py -q`

提交：`feat(门禁): 增加条件激活与严格证据仲裁`。

## 任务 9：强化 Stop Hook、缓存和工作区指纹

**文件：**

- 修改：`entrix/stop_gate/hook.py`
- 修改：`entrix/stop_gate/revalidation.py`
- 修改：`hooks/stop-gate.sh`
- 测试：`tests/stop_gate/test_hook_cli.py`

- [ ] **步骤 1：添加 fail-closed RED 测试**

覆盖 HarnessRunner 构造/运行异常、入口 main 未预期异常、shell 无运行器。Python 层核心断言：

```python
def test_unexpected_hook_error_blocks_configured_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "harness.yaml").write_text(
        '''version: "harness/v1"
evidence_producers:
  - {id: tests, type: test, name: Tests, command: pytest}
gate_policies:
  - name: Tests pass
    severity: hard
    rule: {evidence_id: tests, condition: 'status == "pass"'}
''',
        encoding="utf-8",
    )

    class RaisingRunner:
        def __init__(self, _path: Path, **_kwargs: object) -> None:
            pass

        def run(self, _context: dict[str, object]):
            raise RuntimeError("runner unavailable")

    monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", RaisingRunner)

    rc, output = _run(
        {"session_id": "session", "cwd": str(tmp_path)},
        tmp_path,
        monkeypatch,
    )

    assert rc == 0
    assert json.loads(output)["decision"] == "block"
```

- [ ] **步骤 2：添加 PASS 重跑和失败缓存 RED 测试**

同一 snapshot 连续两次 PASS 断言 Runner 调用两次；连续两次 FAIL 断言调用一次；修改内容、分支、base ref、Harness 或引用环境变量后断言重新运行。

- [ ] **步骤 3：添加嵌套工作区指纹 RED 测试**

在临时父 Git 仓库的 ignored 子目录中创建受检 workspace，修改其中同名文件后断言 fingerprint 改变。该测试替换当前伪非 Git 基线失败用例。

- [ ] **步骤 4：运行并确认 RED**

运行：`python -m pytest tests/stop_gate/test_hook_cli.py -q`

预期：PASS 被缓存、嵌套 ignored workspace 指纹不变或入口异常放行。

- [ ] **步骤 5：实现严格 Hook 和缓存规则**

当配置存在时，所有异常通过 `_write_block_decision()` 输出。只有 `ENTRIX_STOP_GATE_DISABLED` 可提前放行，并向 stderr 输出审计警告。`_save_cached_verdict()` 在 status 为 PASS 时删除旧缓存且不保存。`workspace_fingerprint()` 仅在 `show-toplevel.resolve() == workspace.resolve()` 时使用 Git，否则调用 filesystem fingerprint。

- [ ] **步骤 6：收紧 shell 包装器**

无可用运行器时 stdout 输出一行合法 JSON：

```bash
printf '%s\n' '{"decision":"block","reason":"Entrix Stop Gate 不可用，已按 fail-closed 阻断。"}'
exit 0
```

禁用开关路径保持 exit 0 和空 stdout，但 stderr 写审计警告。

- [ ] **步骤 7：验证 GREEN 并提交**

运行：

```powershell
python -m pytest tests/stop_gate/test_hook_cli.py -q
bash -n hooks/stop-gate.sh
```

提交：`fix(停止门禁): 默认拒绝异常并强制 PASS 重验`。

## 任务 10：增加 Entrix 子命令提示

**文件：**

- 新建：`entrix/cli_hints.py`
- 新建：`tests/test_cli_hints.py`
- 修改：`entrix/cli.py`
- 修改：`tests/test_cli.py`

- [ ] **步骤 1：添加根命令和嵌套命令纠错 RED 测试**

使用真实 parser 调用并捕获 `SystemExit`/stderr，覆盖 `harnes -> harness`、`harness valdate -> harness validate`、`graph impcat -> graph impact`，以及低相似度输入不产生建议：

```python
def test_nested_subcommand_typo_suggests_registered_choice(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as error:
        parser.parse_args(["harness", "valdate"])

    assert error.value.code == 2
    stderr = capsys.readouterr().err
    assert "你是否想输入：entrix harness validate" in stderr


def test_unrelated_subcommand_does_not_guess(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["completely-unrelated"])

    assert "你是否想输入" not in capsys.readouterr().err
```

- [ ] **步骤 2：运行纠错测试并确认 RED**

运行：`python -m pytest tests/test_cli_hints.py -q`

预期：当前 argparse 只输出 invalid choice，没有中文建议。

- [ ] **步骤 3：实现 HintingArgumentParser**

在 `entrix/cli_hints.py` 定义：

```python
class HintingArgumentParser(argparse.ArgumentParser):
    """Argument parser that suggests registered subcommands on close typos."""

    def _check_value(self, action: argparse.Action, value: object) -> None:
        try:
            super()._check_value(action, value)
        except argparse.ArgumentError as error:
            if isinstance(action, argparse._SubParsersAction) and isinstance(value, str):
                choices = list(action.choices)
                matches = difflib.get_close_matches(value, choices, n=1, cutoff=0.72)
                if matches:
                    prefix = tuple(getattr(self, "command_path", ("entrix",)))
                    suggestion = " ".join((*prefix, matches[0]))
                    error.message = f"{error.message}\n你是否想输入：{suggestion}"
            raise
```

`build_parser()` 使用该类；`add_subparsers()` 产生的嵌套 parser 同样继承它。为每个 parser 设置完整 `command_path`，使建议包含正确前缀。

- [ ] **步骤 4：验证纠错 GREEN**

运行：`python -m pytest tests/test_cli_hints.py -q`

预期：高相似度建议通过、低相似度无建议、退出码仍为 2。

- [ ] **步骤 5：添加缺少子命令帮助 RED 测试**

参数化覆盖空 argv、`harness`、`graph`、`hook`、`analyze`。通过可注入 argv 的 `run_cli(argv)` 调用入口，断言退出码 0、stdout 包含当前层 choices、stderr 为空；尤其锁定当前会 AttributeError 的 `harness`。

```python
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], "常用命令"),
        (["harness"], "validate"),
        (["graph"], "impact"),
        (["hook"], "file-length"),
        (["analyze"], "long-file"),
    ],
)
def test_missing_leaf_command_prints_current_group_help(
    argv: list[str], expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli(argv) == 0
    captured = capsys.readouterr()
    assert expected in captured.out
    assert captured.err == ""
```

- [ ] **步骤 6：实现统一缺失子命令处理**

把 `main()` 拆为可测试的 `run_cli(argv: list[str] | None = None) -> int`，`main()` 只调用 `sys.exit(run_cli())`。每个命令组通过 `_help_parser` default 保存自己的 parser；若解析结果没有 `func`，打印该 parser 帮助并返回 0。删除 graph/hook/analyze 特判。

- [ ] **步骤 7：添加下一步提示与机器输出静默 RED 测试**

为 `render_next_steps()` 和 CLI 集成增加测试：成功 `harness validate` 在 stderr 提示 `harness run --json`；返回非 0、`--json`、`--output -`、`stop-gate`、`serve` 不提示；提示不出现在 stdout。

```python
def test_success_hint_uses_stderr_without_polluting_stdout(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("entrix.cli.cmd_harness_validate", lambda _args: 0)

    assert run_cli(["harness", "validate"]) == 0

    captured = capsys.readouterr()
    assert "下一步" not in captured.out
    assert "entrix harness run --json" in captured.err
```

- [ ] **步骤 8：实现声明式下一步映射**

`cli_hints.py` 定义不可变映射和纯函数：

```python
NEXT_STEPS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("init",): ("entrix harness validate harness.yaml", "entrix run"),
    ("harness", "validate"): ("entrix harness run --json",),
    ("run",): ("entrix harness run --json",),
    ("review-trigger",): ("entrix harness run --json",),
}


def should_show_next_steps(args: argparse.Namespace, exit_code: int) -> bool:
    return (
        exit_code == 0
        and not getattr(args, "json", False)
        and getattr(args, "output", None) != "-"
        and tuple(args.command_path) not in {("stop-gate",), ("serve",)}
    )
```

从 `cmd_init()` 删除旧“下一步”打印，改由 `run_cli()` 在 handler 成功后调用 `print_next_steps(..., stream=sys.stderr)`。

- [ ] **步骤 9：验证 GREEN 并提交**

运行：

```powershell
python -m pytest tests/test_cli_hints.py tests/test_cli.py -q
ruff check entrix/cli_hints.py entrix/cli.py tests/test_cli_hints.py
```

提交：`feat(CLI): 增加子命令纠错与下一步提示`。

## 任务 11：完成闭环、模板、文档和全量验证

**文件：**

- 修改：`tests/stop_gate/test_harness_integration.py`
- 修改：`tests/stop_gate/test_integration.py`
- 修改：`harness.yaml`
- 修改：`entrix/harness/template.py`
- 修改：`tests/harness/test_template.py`
- 修改：`README.md`
- 修改：`docs/stop-gate-usage.md`
- 修改：`docs/agent-stop-gate-implementation-status.md`

- [ ] **步骤 1：添加真实 FAIL -> 修改 -> PASS 闭环 RED 测试**

临时仓库配置一个读取实际文件内容并生成 JSON 报告的 command producer。第一次报告 `failed: 1`，断言 Hook block 且 Evidence Bundle 存在；修改输入后第二次报告 `failed: 0`，断言 Hook allow；第三次不修改仍重新调用 producer，证明 PASS 不缓存。

- [ ] **步骤 2：运行闭环测试并确认 RED**

运行：

```powershell
python -m pytest tests/stop_gate/test_harness_integration.py tests/stop_gate/test_integration.py -q
```

- [ ] **步骤 3：更新默认配置和文档**

默认模板增加 `settings.failure_mode: closed`。README 和使用文档给出 JUnit/JSON/SARIF 示例、三级 when、紧急旁路审计说明。历史状态文档标题明确标注已过期，并链接当前设计，不再声称 Stop Hook 未实现。

- [ ] **步骤 4：运行针对性测试并提交**

运行：

```powershell
python -m pytest tests/harness tests/stop_gate -q
python -m entrix harness validate harness.yaml
```

预期：全部通过，配置显示非空 producer/Gate。提交：`docs(门禁): 更新严格 Harness 使用契约`。

- [ ] **步骤 5：执行完整工程验证**

运行并记录完整输出与退出码：

```powershell
python -m pytest -q
ruff check .
mypy entrix/harness entrix/stop_gate/hook.py entrix/stop_gate/runner.py
python -m entrix harness validate harness.yaml
python -m build --no-isolation
git diff --check main...HEAD
git status --short
```

预期：pytest 0 failures；Ruff、Mypy、配置校验、构建和 diff check 均为 exit 0；工作区只包含计划内变更。

- [ ] **步骤 6：请求代码审查并修正发现**

使用 `requesting-code-review` 对 `main...HEAD` 做风险优先审查。若发现问题，先用失败回归测试复现，再做最小修复并重新执行完整验证。

- [ ] **步骤 7：等待用户验收**

向用户提供隔离工作区路径和以下手动检查：真实 Claude Code 插件触发一次 FAIL、修改后 PASS、设置紧急旁路时观察 stderr 审计警告。根据项目规范，在用户明确回复“测试已通过”之前不合并。

## 计划自检映射

| 设计需求 | 覆盖任务 |
| --- | --- |
| fail-closed 与紧急旁路 | 9 |
| 顶层/producer/Gate 三级 when | 1、7、8 |
| skipped/inactive Evidence | 2、7 |
| 六种 parser | 3、4、5、6 |
| artifact 路径安全与接线 | 1、3 |
| Evidence 原子持久化 | 2、7 |
| missing evidence/zero active Gate | 8 |
| PASS 重验、FAIL/BLOCKED 缓存 | 9 |
| 嵌套工作区指纹 | 9 |
| CLI 拼写纠错、命令组帮助和下一步提示 | 10 |
| FAIL -> 修改 -> PASS 闭环 | 11 |
| 文档、模板和全量验证 | 11 |
