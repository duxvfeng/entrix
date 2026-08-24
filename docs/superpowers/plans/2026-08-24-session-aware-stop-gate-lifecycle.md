# 会话感知 Stop Gate 生命周期实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让 Entrix 只在明确任务完成时审查当前 Claude session 的真实改动，并彻底消除普通对话、历史 dirty 文件和并发 session 导致的 Stop Gate 误阻断。

**架构：** 使用用户状态目录中的 session activity ledger 建模任务代次和生命周期，通过 PreToolUse/PostToolUse 建立 session `ChangeSet`，由 TaskCompleted 或显式 ready 触发完成 Gate。Stop、Fitness、Review Trigger、Diff Stats 和 verdict 缓存统一消费冻结后的 `ChangeSet`，不再扫描整个工作区推断任务状态。

**技术栈：** Python 3.11+、dataclasses、JSON、Git CLI、argparse、Claude Code Hooks、pytest、Ruff、mypy、Hatchling。

**设计依据：** `docs/superpowers/specs/2026-08-24-session-aware-stop-gate-lifecycle-design.md`

**开发分支：** `codex/fix-session-aware-stop-gate`，在用户确认本计划后创建；禁止在 `main` 上实施。

---

## 文件职责

### 新建文件

- `entrix/stop_gate/lifecycle.py`：生命周期枚举、session ledger、任务代次、`ChangeSet`、tracking gap 和纯状态转换。
- `entrix/stop_gate/activity.py`：用户状态目录中的 ledger、工具调用快照、文件基线和 verdict 持久化。
- `entrix/stop_gate/change_tracking.py`：workspace 路径校验、文件指纹、结构化编辑工具和 Shell 前后快照归属。
- `entrix/stop_gate/hook_events.py`：Claude 多事件 Hook 分发、事件专用输出契约和完成命令注入。
- `entrix/stop_gate/completion.py`：冻结 `ChangeSet`、构造 Harness 上下文、执行 Gate 和更新 lifecycle/verdict。
- `tests/stop_gate/test_lifecycle.py`：状态机和任务代次单元测试。
- `tests/stop_gate/test_activity.py`：状态 schema、原子持久化、损坏恢复和隔离测试。
- `tests/stop_gate/test_change_tracking.py`：文件归属、提交后 clean worktree、路径安全和快照上限测试。
- `tests/stop_gate/test_hook_events.py`：各 Hook 的输入、输出和失败策略测试。
- `tests/stop_gate/test_completion.py`：完成 Gate、缓存和 tracking gap 集成测试。

### 修改文件

- `entrix/stop_gate/hook.py`：保留 CLI/Stop 兼容入口，删除仓库级完成推断并委托多事件 dispatcher。
- `entrix/stop_gate/phase.py`：将 phase API 迁移到 session lifecycle，不再读写 workspace 共享标记。
- `entrix/stop_gate/revalidation.py`：保留 Harness trust，移除旧 session verdict 所有权或提供 v1 清理迁移。
- `entrix/stop_gate/runner.py`：接收冻结 `ChangeSet` 的文件和 diff 统计。
- `entrix/harness/conditions.py`：增加可复用的 `DiffStats`，与 changed files 一起进入执行上下文。
- `entrix/harness/engine.py`、`entrix/harness/producers/base.py`：把 diff 统计传给 producer。
- `entrix/harness/producers/builtin.py`：Review Trigger 和 Diff Stats 只消费上下文数据。
- `entrix/review_trigger.py`：复用统一 `DiffStats`，保留独立 CLI 的 Git 收集 API。
- `entrix/cli.py`、`entrix/cli_overview.py`：ready、status、doctor、retry 和 reset 的 session 语义。
- `hooks/hooks.json`、`.claude-plugin/plugin.json`：注册七个 lifecycle Hook 并统一走插件二进制启动器。
- `skills/entrix/SKILL.md`：规划、实现、ready 和完成 Gate 的 Agent 协议。
- `README.md`、`docs/stop-gate-usage.md`、`docs/command-reference.md`：新生命周期、恢复和诊断说明。
- `pyproject.toml`、`.claude-plugin/marketplace.json`、`tests/test_plugin_binary_contract.py`：版本提升到 `0.1.25` 并锁定 Hook 契约。

---

## 任务 1：建立生命周期领域模型

**预估工时：** 1.5h

**文件：**

- 创建：`entrix/stop_gate/lifecycle.py`
- 创建：`tests/stop_gate/test_lifecycle.py`

- [ ] **步骤 1：编写状态机失败测试**

先覆盖 Stop 只接受 `ready`、TaskCompleted 可以进入 `ready`、失败后修复仍使用同一 generation、通过后新用户请求创建下一 generation：

```python
from pathlib import Path

from entrix.stop_gate.lifecycle import (
    CompletionAction,
    LifecycleEvent,
    LifecycleState,
    SessionLedger,
    apply_event,
    completion_action,
)


def test_stop_only_runs_gate_for_ready_state(tmp_path: Path) -> None:
    ledger = SessionLedger.new(tmp_path, "session-a")
    implementing = apply_event(ledger, LifecycleEvent.FILE_CHANGED)

    assert implementing.state is LifecycleState.IMPLEMENTING
    assert completion_action(implementing, "Stop") is CompletionAction.ALLOW

    ready = apply_event(implementing, LifecycleEvent.READY_REQUESTED)
    assert completion_action(ready, "Stop") is CompletionAction.RUN_GATE


def test_user_prompt_starts_new_generation_only_after_pass(tmp_path: Path) -> None:
    ledger = SessionLedger.new(tmp_path, "session-a")
    active = apply_event(ledger, LifecycleEvent.FILE_CHANGED)
    continued = apply_event(active, LifecycleEvent.USER_PROMPT)
    passed = apply_event(apply_event(active, LifecycleEvent.READY_REQUESTED), LifecycleEvent.GATE_PASSED)
    next_task = apply_event(passed, LifecycleEvent.USER_PROMPT)

    assert continued.generation == 1
    assert next_task.generation == 2
    assert next_task.state is LifecycleState.OBSERVING
```

- [ ] **步骤 2：运行测试并确认正确红灯**

运行：

```powershell
python -m pytest tests/stop_gate/test_lifecycle.py -q
```

预期：测试收集因 `entrix.stop_gate.lifecycle` 不存在而失败；不得因 fixture、路径或导入当前 checkout 以外的包而失败。

- [ ] **步骤 3：实现最小领域模型和转换表**

实现不可变的状态值、变更统计和 session ledger。转换必须集中在一个显式表中，未知转换抛出 `InvalidLifecycleTransition`：

```python
class LifecycleState(str, Enum):
    OBSERVING = "observing"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    READY = "ready"
    VALIDATING = "validating"
    BLOCKED = "blocked"
    PASSED = "passed"


class CompletionAction(str, Enum):
    ALLOW = "allow"
    RUN_GATE = "run_gate"


@dataclass(frozen=True)
class ChangeStats:
    file_count: int = 0
    added_lines: int = 0
    deleted_lines: int = 0
    binary_files: int = 0


@dataclass(frozen=True)
class TrackingGap:
    code: str
    detail: str
    event_id: str = ""


@dataclass(frozen=True)
class SessionFileChange:
    relative_path: str
    operation: str
    baseline_fingerprint: str | None
    current_fingerprint: str | None
    added_lines: int = 0
    deleted_lines: int = 0
    binary: bool = False
    provenance_events: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangeSet:
    generation: int
    files: tuple[SessionFileChange, ...] = ()
    tracking_gaps: tuple[TrackingGap, ...] = ()

    @property
    def changed_files(self) -> list[str]:
        return [item.relative_path for item in self.files]

    @property
    def stats(self) -> ChangeStats:
        return ChangeStats(
            file_count=len(self.files),
            added_lines=sum(item.added_lines for item in self.files),
            deleted_lines=sum(item.deleted_lines for item in self.files),
            binary_files=sum(item.binary for item in self.files),
        )


@dataclass(frozen=True)
class SessionLedger:
    schema_version: str
    workspace: Path
    session_id: str
    generation: int
    state: LifecycleState
    change_set: ChangeSet
    ready_source: str | None = None

    @classmethod
    def new(cls, workspace: Path, session_id: str) -> "SessionLedger":
        return cls(
            schema_version="stop-gate-ledger/v1",
            workspace=workspace.resolve(),
            session_id=session_id,
            generation=1,
            state=LifecycleState.OBSERVING,
            change_set=ChangeSet(generation=1),
        )


def completion_action(ledger: SessionLedger, event_name: str) -> CompletionAction:
    if event_name == "TaskCompleted":
        return CompletionAction.RUN_GATE
    if event_name == "Stop" and ledger.state is LifecycleState.READY:
        return CompletionAction.RUN_GATE
    return CompletionAction.ALLOW
```

`SessionLedger.new()` 固定从 generation 1、`observing` 开始；`apply_event()` 使用 `dataclasses.replace()` 返回新对象，不原地修改输入。

- [ ] **步骤 4：验证绿灯并执行范围 lint**

```powershell
python -m pytest tests/stop_gate/test_lifecycle.py -q
ruff check entrix/stop_gate/lifecycle.py tests/stop_gate/test_lifecycle.py
mypy entrix/stop_gate/lifecycle.py
```

预期：测试全部 PASS，Ruff 和 mypy 均无输出错误。

- [ ] **步骤 5：提交领域模型**

```powershell
git add entrix/stop_gate/lifecycle.py tests/stop_gate/test_lifecycle.py
git commit -m "feat(stop-gate): 添加会话生命周期模型"
```

## 任务 2：实现 session activity ledger

**预估工时：** 3h

**文件：**

- 创建：`entrix/stop_gate/activity.py`
- 创建：`tests/stop_gate/test_activity.py`
- 修改：`tests/conftest.py`

- [ ] **步骤 1：编写持久化和隔离失败测试**

覆盖 round-trip、session 隔离、通过后 generation 递增、损坏状态记录诊断、状态路径不进入 workspace：

```python
def test_activity_store_isolates_sessions_and_generations(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = ActivityStore(tmp_path / "state")

    first = store.start_session(workspace, "session-a")
    second = store.start_session(workspace, "session-b")
    store.save(replace(first, state=LifecycleState.PASSED))
    next_task = store.on_user_prompt(workspace, "session-a")

    assert next_task.generation == 2
    assert store.load(workspace, "session-b") == second
    assert not (workspace / ".harness" / "runtime" / "phase.json").exists()


def test_corrupt_ledger_is_not_treated_as_valid(tmp_path: Path) -> None:
    store = ActivityStore(tmp_path / "state")
    workspace = tmp_path / "repo"
    workspace.mkdir()
    path = store.ledger_path(workspace, "session-a")
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")

    loaded = store.load_result(workspace, "session-a")

    assert loaded.ledger is None
    assert loaded.gap is not None
    assert loaded.gap.code == "ledger_corrupt"
```

- [ ] **步骤 2：运行测试确认红灯**

```powershell
python -m pytest tests/stop_gate/test_activity.py -q
```

预期：因 `ActivityStore` 尚不存在而失败。

- [ ] **步骤 3：实现 schema v1、原子写入和 generation API**

实现以下公开接口，状态路径为 `state/lifecycle/<workspace_sha>/<session_sha>/ledger.json`：

```python
LEDGER_SCHEMA_VERSION = "stop-gate-ledger/v1"


@dataclass(frozen=True)
class LoadResult:
    ledger: SessionLedger | None
    gap: TrackingGap | None = None


class ActivityStore:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = Path(state_dir) if state_dir else _default_state_dir()

    def start_session(self, workspace: Path, session_id: str) -> SessionLedger:
        ledger = SessionLedger.new(workspace.resolve(), session_id)
        self.save(ledger)
        return ledger

    def on_user_prompt(self, workspace: Path, session_id: str) -> SessionLedger:
        current = self.load(workspace, session_id) or SessionLedger.new(workspace, session_id)
        updated = apply_event(current, LifecycleEvent.USER_PROMPT)
        self.save(updated)
        return updated

    def save(self, ledger: SessionLedger) -> None:
        target = self.ledger_path(ledger.workspace, ledger.session_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(self._serialize(ledger), encoding="utf-8")
        temporary.replace(target)

    def load(self, workspace: Path, session_id: str) -> SessionLedger | None:
        return self.load_result(workspace, session_id).ledger
```

序列化必须校验 schema、绝对 workspace、session id、枚举值、generation 正整数和 TTL；无效状态返回 `LoadResult.gap`，不得降级读取 `.harness/runtime/phase.json`。

- [ ] **步骤 4：增加临时快照目录和安全清理测试**

新增测试确认 `snapshot_path()` 使用哈希目录，`reset_session()` 只能删除状态根内当前 session，过期状态清理不会跟随 workspace 外符号链接。实现单文件 2 MiB、任务总量 20 MiB、默认 TTL 8 小时常量。

- [ ] **步骤 5：运行 store 测试和 lint**

```powershell
python -m pytest tests/stop_gate/test_activity.py -q
ruff check entrix/stop_gate/activity.py tests/stop_gate/test_activity.py tests/conftest.py
mypy entrix/stop_gate/activity.py entrix/stop_gate/lifecycle.py
```

并发隔离通过测试内启动两个独立进程写不同 session 验证，不引入项目未声明的 pytest 插件。

- [ ] **步骤 6：提交 activity ledger**

```powershell
git add entrix/stop_gate/activity.py tests/stop_gate/test_activity.py tests/conftest.py
git commit -m "feat(stop-gate): 持久化会话活动账本"
```

## 任务 3：实现当前 session 的文件变更归属

**预估工时：** 4h

**文件：**

- 创建：`entrix/stop_gate/change_tracking.py`
- 创建：`tests/stop_gate/test_change_tracking.py`
- 修改：`entrix/stop_gate/activity.py`
- 修改：`entrix/stop_gate/lifecycle.py`

- [ ] **步骤 1：编写结构化编辑工具失败测试**

使用真实临时文件验证首次触摸基线、净变化、删除和 workspace 逃逸：

```python
def test_edit_event_records_only_the_file_changed_by_this_session(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    owned = workspace / "owned.py"
    existing = workspace / "existing.py"
    owned.write_text("value = 1\n", encoding="utf-8")
    existing.write_text("dirty before session\n", encoding="utf-8")
    tracker = ChangeTracker(ActivityStore(tmp_path / "state"))

    tracker.capture_pre(workspace, "session-a", "tool-1", "Edit", {"file_path": str(owned)})
    owned.write_text("value = 2\n", encoding="utf-8")
    change_set = tracker.capture_post(
        workspace, "session-a", "tool-1", "Edit", {"file_path": str(owned)}
    )

    assert change_set.changed_files == ["owned.py"]
    assert change_set.files[0].added_lines == 1
    assert change_set.files[0].deleted_lines == 1


def test_tool_path_outside_workspace_records_gap_without_snapshot(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret\n", encoding="utf-8")
    tracker = ChangeTracker(ActivityStore(tmp_path / "state"))

    result = tracker.capture_pre(
        workspace, "session-a", "tool-1", "Write", {"file_path": str(outside)}
    )

    assert result.gap is not None
    assert result.gap.code == "path_outside_workspace"
```

- [ ] **步骤 2：编写 Shell 和 commit 失败测试**

在临时 Git 仓库中先提交基线，再让一个 Shell 工具窗口修改并提交文件。断言 worktree clean 后 `ChangeSet` 仍包含该文件；另一个 session 修改的文件和调用前未变化的 dirty 文件不得混入。

运行：

```powershell
python -m pytest tests/stop_gate/test_change_tracking.py -q
```

预期：因 `ChangeTracker` 不存在而失败。

- [ ] **步骤 3：实现安全路径、指纹和工具前后快照**

核心接口固定如下：

```python
@dataclass(frozen=True)
class FileFingerprint:
    exists: bool
    sha256: str | None
    size: int = 0
    binary: bool = False


@dataclass(frozen=True)
class ToolSnapshot:
    event_id: str
    tool_name: str
    head: str | None
    candidates: dict[str, FileFingerprint]


@dataclass(frozen=True)
class TrackingResult:
    change_set: ChangeSet
    gap: TrackingGap | None = None


class ChangeTracker:
    def capture_pre(
        self,
        workspace: Path,
        session_id: str,
        event_id: str,
        tool_name: str,
        tool_input: dict[str, object],
    ) -> TrackingResult:
        candidate_paths = self._candidate_paths(workspace, tool_name, tool_input)
        snapshot = self._snapshot(workspace, event_id, tool_name, candidate_paths)
        self.store.save_tool_snapshot(workspace, session_id, snapshot)
        return TrackingResult(change_set=self.store.freeze(workspace, session_id))

    def capture_post(
        self,
        workspace: Path,
        session_id: str,
        event_id: str,
        tool_name: str,
        tool_input: dict[str, object],
    ) -> ChangeSet:
        before = self.store.load_tool_snapshot(workspace, session_id, event_id)
        candidates = self._post_candidates(workspace, before, tool_input)
        event = self._compare(workspace, before, candidates)
        return self.store.record_change_event(workspace, session_id, event)
```

Shell 候选集由调用前 dirty、调用后 dirty、`before_head..after_head` 和显式路径并集产生，再比较前后内容指纹。直接工具只解析已知路径字段。任何解析失败写入稳定 gap code，不扫描或纳入无法证明归属的全仓库文件。

- [ ] **步骤 4：实现首触基线和净 diff 统计**

文本基线保存到状态目录并使用 `difflib.SequenceMatcher` 计算最终净增删行；二进制只记录指纹。达到快照上限时写入 `snapshot_file_limit` 或 `snapshot_task_limit`，不得读取超限内容到内存。

- [ ] **步骤 5：运行归属、路径和静态检查**

```powershell
python -m pytest tests/stop_gate/test_change_tracking.py tests/stop_gate/test_activity.py -q
ruff check entrix/stop_gate/change_tracking.py entrix/stop_gate/activity.py tests/stop_gate/test_change_tracking.py
mypy entrix/stop_gate/change_tracking.py entrix/stop_gate/activity.py entrix/stop_gate/lifecycle.py
```

预期：session 归属矩阵全部 PASS，静态检查无错误。

- [ ] **步骤 6：提交变更归属实现**

```powershell
git add entrix/stop_gate/change_tracking.py entrix/stop_gate/activity.py entrix/stop_gate/lifecycle.py tests/stop_gate/test_change_tracking.py
git commit -m "feat(stop-gate): 跟踪当前会话文件变更"
```

## 任务 4：接入 Claude 多事件 Hook

**预估工时：** 3h

**文件：**

- 创建：`entrix/stop_gate/hook_events.py`
- 创建：`tests/stop_gate/test_hook_events.py`
- 修改：`entrix/stop_gate/hook.py`
- 修改：`entrix/cli.py`

- [ ] **步骤 1：编写事件路由和普通对话失败测试**

覆盖无 Harness 快速放行、SessionStart 建账本、UserPromptSubmit 注入精确 ready 命令、Pre/Post 调 tracker、非 ready Stop 放行、`stop_hook_active` 在读取状态前放行：

```python
def test_non_ready_stop_allows_without_running_gate(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
    store = ActivityStore(tmp_path / "state")
    ledger = store.start_session(tmp_path, "session-a")
    store.save(replace(ledger, state=LifecycleState.IMPLEMENTING))
    run_gate = Mock()
    monkeypatch.setattr("entrix.stop_gate.hook_events.run_completion_gate", run_gate)

    result = dispatch_hook(
        {"hook_event_name": "Stop", "session_id": "session-a", "cwd": str(tmp_path)},
        state_dir=tmp_path / "state",
    )

    assert result.exit_code == 0
    assert result.stdout is None
    run_gate.assert_not_called()


def test_stop_hook_active_short_circuits_before_state_read(tmp_path: Path, monkeypatch) -> None:
    load = Mock(side_effect=AssertionError("state must not be read"))
    monkeypatch.setattr(ActivityStore, "load_result", load)

    result = dispatch_hook(
        {"hook_event_name": "Stop", "stop_hook_active": True, "cwd": str(tmp_path)}
    )

    assert result.exit_code == 0
    assert result.stdout is None
    load.assert_not_called()
```

- [ ] **步骤 2：编写 TaskCompleted 与事件输出契约失败测试**

固定 `HookResult` 契约：Stop 失败为 exit 0 + block JSON；TaskCompleted 失败为 exit 2 + stderr；UserPromptSubmit additional context 使用 `hookSpecificOutput.hookEventName` 和 `additionalContext`；其余跟踪事件成功时无 stdout。

运行：

```powershell
python -m pytest tests/stop_gate/test_hook_events.py -q
```

预期：因 dispatcher 不存在而失败。

- [ ] **步骤 3：实现 dispatcher 和事件适配器**

实现稳定返回模型和显式 dispatch table：

```python
@dataclass(frozen=True)
class HookResult:
    exit_code: int = 0
    stdout: dict[str, object] | None = None
    stderr: str = ""


HookHandler = Callable[[dict[str, object], Path, ActivityStore], HookResult]


HANDLERS: dict[str, HookHandler] = {
    "SessionStart": handle_session_start,
    "UserPromptSubmit": handle_user_prompt,
    "PreToolUse": handle_pre_tool,
    "PostToolUse": handle_post_tool,
    "TaskCompleted": handle_task_completed,
    "Stop": handle_stop,
    "SessionEnd": handle_session_end,
}


def dispatch_hook(payload: dict[str, object], *, state_dir: Path | None = None) -> HookResult:
    if payload.get("stop_hook_active") is True:
        return HookResult()
    workspace = Path(str(payload.get("cwd") or Path.cwd())).resolve()
    if find_harness_config(workspace) is None:
        return HookResult()
    event_name = str(payload.get("hook_event_name") or "")
    handler = HANDLERS.get(event_name)
    if handler is None:
        return HookResult(exit_code=1, stderr=f"unsupported Entrix hook event: {event_name}")
    return handler(payload, workspace, ActivityStore(state_dir))
```

`hook.py` 只负责 JSON stdin/stdout/stderr 和 CLI 参数；新增 `entrix hook` 命令，`entrix stop-gate` 作为相同 dispatcher 的兼容别名。

- [ ] **步骤 4：验证事件测试和旧 Stop 契约测试**

```powershell
python -m pytest tests/stop_gate/test_hook_events.py tests/stop_gate/test_hook_cli.py -q
ruff check entrix/stop_gate/hook_events.py entrix/stop_gate/hook.py tests/stop_gate/test_hook_events.py
mypy entrix/stop_gate/hook_events.py entrix/stop_gate/hook.py
```

旧测试中依赖“任意 workspace dirty 即运行”的断言应改写为显式 ledger/ready 前置条件；fail-closed、无配置放行和 `stop_hook_active` 回归必须保留。

- [ ] **步骤 5：提交多事件分发**

```powershell
git add entrix/stop_gate/hook_events.py entrix/stop_gate/hook.py entrix/cli.py tests/stop_gate/test_hook_events.py tests/stop_gate/test_hook_cli.py
git commit -m "feat(stop-gate): 接入任务生命周期事件"
```

## 任务 5：让完成 Gate 和缓存消费冻结 ChangeSet

**预估工时：** 1.5h

**文件：**

- 创建：`entrix/stop_gate/completion.py`
- 创建：`tests/stop_gate/test_completion.py`
- 修改：`entrix/stop_gate/revalidation.py`
- 修改：`entrix/stop_gate/runner.py`
- 修改：`tests/stop_gate/test_harness_integration.py`

- [ ] **步骤 1：编写完成 Gate 和缓存失败测试**

验证 no-op pass、不完整 tracking gap 阻断、TaskCompleted/ready 共享执行路径、generation 和内容变化使缓存失效：

```python
def ready_ledger(
    workspace: Path,
    session_id: str,
    *,
    changed_files: tuple[str, ...] = (),
    gaps: tuple[TrackingGap, ...] = (),
) -> SessionLedger:
    files = tuple(
        SessionFileChange(
            relative_path=path,
            operation="modify",
            baseline_fingerprint="before",
            current_fingerprint="after",
        )
        for path in changed_files
    )
    ledger = SessionLedger.new(workspace, session_id)
    return replace(
        ledger,
        state=LifecycleState.READY,
        change_set=ChangeSet(generation=1, files=files, tracking_gaps=gaps),
        ready_source="explicit",
    )


def pass_result() -> RunResult:
    return RunResult(verdict=Verdict(status=VerdictStatus.PASS, summary="ok"))


def test_completion_uses_only_frozen_session_changes(tmp_path: Path, monkeypatch) -> None:
    store = ActivityStore(tmp_path / "state")
    ledger = ready_ledger(tmp_path, "session-a", changed_files=("owned.py",))
    store.save(ledger)
    contexts: list[dict[str, object]] = []
    monkeypatch.setattr(HarnessRunner, "run", lambda _self, context: contexts.append(context) or pass_result())

    result = run_completion_gate(ledger, store=store, config_path=tmp_path / "harness.yaml")

    assert result.allowed is True
    assert contexts[0]["changed_files"] == ["owned.py"]
    assert contexts[0]["task_id"] == "session-a:1"


def test_tracking_gap_fails_closed_before_runner(tmp_path: Path, monkeypatch) -> None:
    ledger = ready_ledger(tmp_path, "session-a", gaps=(TrackingGap("snapshot_file_limit", "large.py"),))
    run = Mock()
    monkeypatch.setattr(HarnessRunner, "run", run)

    result = run_completion_gate(ledger, store=ActivityStore(tmp_path / "state"), config_path=tmp_path / "harness.yaml")

    assert result.allowed is False
    assert result.reason_code == "change_set_incomplete"
    run.assert_not_called()
```

- [ ] **步骤 2：运行测试确认红灯**

```powershell
python -m pytest tests/stop_gate/test_completion.py -q
```

预期：因 completion orchestration 不存在而失败。

- [ ] **步骤 3：实现冻结、Gate 上下文和 schema v2 缓存**

`CompletionResult` 固定包含 `allowed`、`reason`、`reason_code` 和可选 feedback。缓存路径加入 generation，指纹材料使用规范 JSON：

```python
def verdict_fingerprint(
    ledger: SessionLedger,
    change_set: ChangeSet,
    *,
    branch: str,
    base_ref: str,
    config_sha256: str,
    environment_sha256: str,
) -> str:
    material = {
        "schema": "stop-gate-verdict/v2",
        "session_id": ledger.session_id,
        "generation": ledger.generation,
        "branch": branch,
        "base_ref": base_ref,
        "config": config_sha256,
        "environment": environment_sha256,
        "files": [asdict(item) for item in change_set.files],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

无文件变化直接将 ledger 标记 `passed`，不构造 Runner。存在 gap 时在 runner 前阻断。执行时先标记 `validating`，异常、超时和非 pass verdict 标记 `blocked`；pass 标记 `passed` 并删除首触快照。

- [ ] **步骤 4：运行完成闭环和集成测试**

```powershell
python -m pytest tests/stop_gate/test_completion.py tests/stop_gate/test_harness_integration.py -q
ruff check entrix/stop_gate/completion.py entrix/stop_gate/revalidation.py entrix/stop_gate/runner.py
mypy entrix/stop_gate/completion.py entrix/stop_gate/revalidation.py entrix/stop_gate/runner.py
```

- [ ] **步骤 5：提交完成 Gate**

```powershell
git add entrix/stop_gate/completion.py entrix/stop_gate/revalidation.py entrix/stop_gate/runner.py tests/stop_gate/test_completion.py tests/stop_gate/test_harness_integration.py
git commit -m "fix(stop-gate): 按会话变更执行完成门禁"
```

## 任务 6：统一 Harness、Review Trigger 和 Diff Stats 数据

**预估工时：** 2h

**文件：**

- 修改：`entrix/harness/conditions.py`
- 修改：`entrix/harness/engine.py`
- 修改：`entrix/harness/producers/base.py`
- 修改：`entrix/harness/producers/builtin.py`
- 修改：`entrix/review_trigger.py`
- 修改：`tests/harness/test_builtin_producers.py`
- 修改：`tests/harness/test_engine.py`
- 修改：`tests/test_review_trigger.py`

- [ ] **步骤 1：编写 producer 不重扫仓库的失败测试**

将 `collect_changed_files` 和 `collect_diff_stats` monkeypatch 为抛错，并传入 session 数据：

```python
def test_review_trigger_consumes_session_change_context(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "entrix.review_trigger.collect_changed_files",
        Mock(side_effect=AssertionError("producer must not rescan git")),
    )
    producer = EntrixReviewTriggerProducer(
        EvidenceProducerConfig(
            id="review",
            type="review-trigger",
            name="Session review",
            builtin="entrix-review-trigger",
        ),
        [
            ReviewTriggerRule(
                name="owned",
                type="sensitive_file_change",
                paths=("owned.py",),
            )
        ],
    )
    context = ProducerContext(
        task_id="session-a:1",
        repo_root=tmp_path,
        when_context=WhenContext(
            repo_root=tmp_path,
            changed_files=["owned.py"],
            diff_stats=DiffStats(file_count=1, added_lines=3, deleted_lines=1),
        ),
    )

    evidence = producer.run(context)

    assert evidence.raw["changed_files"] == ["owned.py"]
    assert evidence.raw["diff_stats"]["added_lines"] == 3
```

- [ ] **步骤 2：运行测试确认红灯**

```powershell
python -m pytest tests/harness/test_builtin_producers.py -q
```

预期：现有 Review Trigger producer 调用 Git 收集函数，测试按预期失败。

- [ ] **步骤 3：把 DiffStats 放入 WhenContext 并贯穿 engine**

在 `entrix.harness.conditions` 定义统一类型，并让 engine 原样传递同一个 `WhenContext`：

```python
@dataclass(frozen=True)
class DiffStats:
    file_count: int = 0
    added_lines: int = 0
    deleted_lines: int = 0
    binary_files: int = 0


@dataclass
class WhenContext:
    repo_root: Path = field(default_factory=Path.cwd)
    changed_files: list[str] | None = None
    current_branch: str | None = None
    diff_stats: DiffStats | None = None
```

`review_trigger.py` 导入并重新导出该类型以保持现有调用兼容。Review producer 使用 `when_context.changed_files` 和 `when_context.diff_stats`；Diff Stats producer 直接序列化相同统计；缺少统计时返回明确 `skipped` evidence，不运行 Git。

- [ ] **步骤 4：运行 Harness 和 review-trigger 测试**

```powershell
python -m pytest tests/harness/test_builtin_producers.py tests/harness/test_engine.py tests/test_review_trigger.py -q
ruff check entrix/harness entrix/review_trigger.py tests/harness/test_builtin_producers.py
mypy entrix/harness entrix/review_trigger.py
```

- [ ] **步骤 5：提交数据一致性修改**

```powershell
git add entrix/harness/conditions.py entrix/harness/engine.py entrix/harness/producers/base.py entrix/harness/producers/builtin.py entrix/review_trigger.py tests/harness/test_builtin_producers.py tests/harness/test_engine.py tests/test_review_trigger.py
git commit -m "fix(harness): 统一会话变更上下文"
```

## 任务 7：迁移 phase、status、doctor 和 retry CLI

**预估工时：** 1.5h

**文件：**

- 修改：`entrix/stop_gate/phase.py`
- 修改：`entrix/cli.py`
- 修改：`entrix/cli_overview.py`
- 修改：`tests/stop_gate/test_phase.py`
- 修改：`tests/test_cli.py`
- 修改：`tests/test_cli_hints.py`

- [ ] **步骤 1：编写 CLI 迁移失败测试**

覆盖无 session id 拒绝写共享 phase、ready 转换、status JSON、doctor tracking gap、retry 保留 `ChangeSet`、clear 完全重置当前 session：

```python
def test_phase_requires_session_id_and_never_writes_workspace_marker(tmp_path, capsys) -> None:
    args = argparse.Namespace(repo=str(tmp_path), mode="implementation", session_id=None)

    assert cli_module.cmd_phase(args) == 2
    assert "--session-id" in capsys.readouterr().err
    assert not (tmp_path / ".harness" / "runtime" / "phase.json").exists()


def test_status_json_exposes_lifecycle_and_owned_files(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("ENTRIX_STATE_DIR", str(tmp_path / "state"))
    store = ActivityStore()
    ledger = SessionLedger.new(tmp_path, "session-a")
    change = SessionFileChange(
        relative_path="entrix/model.py",
        operation="modify",
        baseline_fingerprint="before",
        current_fingerprint="after",
    )
    store.save(
        replace(
            ledger,
            state=LifecycleState.READY,
            change_set=ChangeSet(generation=1, files=(change,)),
            ready_source="explicit",
        )
    )

    assert cli_module.run_cli(
        ["status", "--repo", str(tmp_path), "--session-id", "session-a", "--json"]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["lifecycle"]["state"] == "ready"
    assert payload["lifecycle"]["changed_files"] == ["entrix/model.py"]
```

- [ ] **步骤 2：运行 CLI 测试确认红灯**

```powershell
python -m pytest tests/stop_gate/test_phase.py tests/test_cli.py -k "phase or status or doctor or retry" -q
```

预期：ready 不在 parser choices，status 仍返回 workspace phase，新增字段测试失败。

- [ ] **步骤 3：实现 session-only phase 兼容层和诊断输出**

`phase.py` 保留公开函数名，但所有读写委托 `ActivityStore`；`write_phase()` 缺 session id 抛出 `ValueError`。CLI choices 改为 `planning|implementation|ready|clear`，并把 lifecycle 状态、generation、ready source、文件、gaps、verdict 放入 status JSON。

`doctor` 检查状态目录、ledger schema、过期 validating、legacy phase 文件和插件 Hook 集合。`retry` 只删除当前 generation verdict 并把 `blocked` 改回 `implementing`；`phase clear` 调用 `reset_session()`。

- [ ] **步骤 4：运行 CLI、帮助和 mypy**

```powershell
python -m pytest tests/stop_gate/test_phase.py tests/test_cli.py tests/test_cli_hints.py -q
python -m entrix phase --help
python -m entrix status --repo . --session-id manual --json
ruff check entrix/stop_gate/phase.py entrix/cli.py entrix/cli_overview.py tests/test_cli.py
mypy entrix/stop_gate/phase.py entrix/cli_overview.py
```

预期：测试 PASS；帮助列出 ready；status 输出合法 JSON；lint/type check 无错误。

- [ ] **步骤 5：提交 CLI 迁移**

```powershell
git add entrix/stop_gate/phase.py entrix/cli.py entrix/cli_overview.py tests/stop_gate/test_phase.py tests/test_cli.py tests/test_cli_hints.py
git commit -m "feat(cli): 增加会话门禁诊断命令"
```

## 任务 8：发布插件 Hook 配置并更新使用协议

**预估工时：** 1.5h

**文件：**

- 修改：`hooks/hooks.json`
- 修改：`.claude-plugin/plugin.json`
- 修改：`.claude-plugin/marketplace.json`
- 修改：`skills/entrix/SKILL.md`
- 修改：`README.md`
- 修改：`docs/stop-gate-usage.md`
- 修改：`docs/command-reference.md`
- 修改：`pyproject.toml`
- 修改：`tests/test_plugin_binary_contract.py`
- 修改：`tests/test_bump_version.py`

- [ ] **步骤 1：编写插件契约和文档失败测试**

将 Hook 契约锁定为七个事件、同一二进制入口和分层超时：

```python
def test_plugin_registers_session_aware_hook_events() -> None:
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))

    assert set(plugin["hooks"]) == {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "TaskCompleted",
        "Stop",
        "SessionEnd",
    }
    for event, groups in plugin["hooks"].items():
        hook = groups[0]["hooks"][0]
        assert hook["command"] == "node"
        assert hook["args"] == ["${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs", "hook"]
        assert hook["timeout"] == (295 if event in {"TaskCompleted", "Stop"} else 10)
```

- [ ] **步骤 2：运行契约测试确认红灯**

```powershell
python -m pytest tests/test_plugin_binary_contract.py tests/test_bump_version.py -q
```

预期：当前 manifest 只有 Stop，事件集合断言失败。

- [ ] **步骤 3：更新 Hook manifests、skill 和文档**

`hooks/hooks.json` 与 plugin manifest 使用相同事件映射。Pre/Post matcher 只覆盖 `Edit|Write|NotebookEdit|Bash`；其他事件 matcher 按 Claude Code schema 使用允许的通配形式。TaskCompleted 和 Stop 使用 295 秒，跟踪事件使用 10 秒。

skill 必须说明：规划设置 planning，批准实现设置 implementation，准备最终回复设置带 session id 的 ready；禁止在实现中途设置 ready；`stop_hook_active` 重试不再次阻断。README 和指南增加普通对话、并发 session、tracking gap、status/doctor/retry/reset 示例。

- [ ] **步骤 4：使用版本脚本提升到 0.1.25**

```powershell
python scripts/bump_version.py 0.1.25
```

预期：只更新 `pyproject.toml`、plugin manifest、marketplace 和版本契约测试中的固定版本；输出每个文件的替换计数。

- [ ] **步骤 5：运行插件、版本和文档契约测试**

```powershell
python -m pytest tests/test_plugin_binary_contract.py tests/test_bump_version.py tests/test_cli_hints.py -q
python -m entrix --help
git diff --check
```

预期：所有契约 PASS，帮助包含 ready/status/doctor，差异无空白错误。

- [ ] **步骤 6：提交插件和文档**

```powershell
git add hooks/hooks.json .claude-plugin/plugin.json .claude-plugin/marketplace.json skills/entrix/SKILL.md README.md docs/stop-gate-usage.md docs/command-reference.md pyproject.toml tests/test_plugin_binary_contract.py tests/test_bump_version.py
git commit -m "feat(plugin): 发布会话感知门禁事件"
```

## 任务 9：严格 lint、全量验证和代码审查

**预估工时：** 1h

**文件：**

- 修改：仅修复本分支引入的验证或审查问题
- 创建：`docs/testing/2026-08-24-session-aware-stop-gate.tdd.md`

- [ ] **步骤 1：运行 Stop Gate 与 Harness 重点测试**

```powershell
python -m pytest tests/stop_gate tests/harness/test_builtin_producers.py tests/harness/test_engine.py tests/test_review_trigger.py tests/test_cli.py tests/test_plugin_binary_contract.py -q
```

预期：全部 PASS，无 warning、资源泄漏或后台进程残留。

- [ ] **步骤 2：严格执行格式和 lint 审查**

```powershell
ruff format --check .
ruff check .
mypy
git diff --check
```

预期：四条命令退出码均为 0。禁止通过新增 `noqa`、扩大 mypy exclude、降低 Ruff 规则或删除测试规避失败。

- [ ] **步骤 3：运行全量测试并生成 JUnit**

```powershell
python -m pytest -q --junitxml=.artifacts/pytest.xml
```

预期：全量测试 PASS；`.artifacts/pytest.xml` 存在且不提交 Git。

- [ ] **步骤 4：验证构建和 Harness 配置**

```powershell
python -m build --no-isolation
python -m entrix harness validate harness.yaml
python -m entrix run --tier normal --scope local --min-score 0
python -m entrix harness run --config harness.yaml --json
```

预期：构建成功、配置有效；两个 Entrix 检查按 `harness.yaml` 返回可解释结果。若 Harness 因本项目策略要求人工审查，不得伪称通过，应记录具体 gate 和 evidence。

- [ ] **步骤 5：执行需求和代码审查**

逐项对照设计第 16 节验收矩阵，并重点审查：

- `stop_hook_active` 是否在任何状态 I/O 之前；
- 普通对话和非 ready Stop 是否完全不构造 Runner；
- workspace 逃逸和符号链接是否被拒绝；
- Review Trigger 是否仍有 completion 路径的 Git 重扫；
- session/generation 是否进入状态路径和缓存键；
- tracking gap 是否只在完成路径 fail-closed；
- `.claude/settings.local.json`、`.artifacts/`、构建产物是否未提交。

- [ ] **步骤 6：记录验证证据**

在 `docs/testing/2026-08-24-session-aware-stop-gate.tdd.md` 记录每个 TDD 红灯的失败原因、对应绿灯命令、最终命令退出码和剩余风险。不得只写“测试通过”。

- [ ] **步骤 7：提交验证记录和必要修复**

```powershell
git add docs/testing/2026-08-24-session-aware-stop-gate.tdd.md
git commit -m "test(stop-gate): 记录会话门禁验收证据"
```

若审查产生代码修复，应与对应回归测试一起单独提交，不得塞入验证文档提交。

---

## 里程碑与完成定义

| 里程碑 | 对应任务 | 完成定义 |
| --- | --- | --- |
| M1 生命周期与账本 | 1-2 | session/generation 状态可原子持久化且不写 workspace |
| M2 变更归属 | 3 | dirty 基线、并发 session、提交后 clean 和路径安全测试通过 |
| M3 Hook 与 Gate | 4-5 | TaskCompleted/ready 运行 Gate，普通 Stop 和 active 重试放行 |
| M4 数据与诊断 | 6-7 | producer 共享 `ChangeSet`，CLI 可诊断和恢复当前 session |
| M5 发布与验收 | 8-9 | 插件契约、版本、文档、全量测试、lint、mypy 和构建完成 |

代码实现结束后，AI 只报告本机验证证据和剩余风险，不自行合并。必须由用户完成本地验收并明确回复“测试通过”，才可将开发分支合并到本地 `main`。
