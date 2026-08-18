# 阶段感知 Stop Gate 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让 Stop Gate 只在实现阶段或存在工作区变更时运行，跳过纯头脑风暴和 `entrix init` 的当前回合。

**架构：** 用工作区运行时的短期阶段标记表达 `planning`、`implementation` 和一次性 `init` 意图；Stop Hook 在现有 Harness 流程前先处理标记和变更检测。没有标记时，有变更仍走原有门禁，保持直接编辑兼容。

**技术栈：** Python 3.10+、JSON、argparse、pytest、现有 Stop Hook 状态存储。

---

## 文件职责

- `entrix/stop_gate/phase.py`：阶段状态格式、原子写入、读取、过期和一次性消费。
- `entrix/stop_gate/hook.py`：在现有 Stop Gate 前执行阶段和工作区变更判定。
- `entrix/cli.py`：增加 `phase` 命令，并让 `init` 写入一次性初始化标记。
- `skills/entrix/SKILL.md`：规划阶段设置 `planning`，批准实现后设置 `implementation`。
- `tests/stop_gate/test_phase.py`：阶段状态单元测试。
- `tests/stop_gate/test_hook_cli.py`：Stop Hook 阶段触发回归测试。
- `tests/test_cli.py`：阶段 CLI 和 init 标记测试。
- `docs/stop-gate-usage.md`、`README.md`：记录阶段触发语义。

### 任务 1：实现阶段状态存储

**文件：**

- 创建：`entrix/stop_gate/phase.py`
- 创建：`tests/stop_gate/test_phase.py`

- [x] **步骤 1：编写失败测试**

覆盖以下行为：写入后读取模式；路径不匹配返回空；过期状态返回空并清理；一次性 `init` 状态只被消费一次；写入使用临时文件替换目标文件。

- [x] **步骤 2：运行测试确认失败**

```powershell
python -m pytest tests/stop_gate/test_phase.py -q
```

预期：因 `entrix.stop_gate.phase` 尚不存在而失败。

- [x] **步骤 3：实现最小状态 API**

实现以下接口：

```python
def write_phase(workspace: Path, mode: str, *, one_shot: bool = False, ttl_seconds: int = 28800) -> None: ...
def read_phase(workspace: Path) -> str | None: ...
def consume_phase(workspace: Path, mode: str) -> bool: ...
```

只允许 `planning`、`implementation`、`init`；使用 UTC ISO 时间、工作区绝对路径和原子替换。

- [x] **步骤 4：运行测试确认通过**

```powershell
python -m pytest tests/stop_gate/test_phase.py -q
```

预期：所有阶段状态测试通过。

### 任务 2：让 Stop Hook 按阶段和变更触发

**文件：**

- 修改：`entrix/stop_gate/hook.py`
- 修改：`tests/stop_gate/test_hook_cli.py`

- [x] **步骤 1：编写失败测试**

新增四个测试：无变更且无阶段标记时不构造 Runner；`planning` 有变更时不构造 Runner；`implementation` 无变更时构造 Runner；`init` 标记跳过并被消费。保留已有“有变更时构造 Runner”和失败阻断测试。

- [x] **步骤 2：运行测试确认失败**

```powershell
python -m pytest tests/stop_gate/test_hook_cli.py -q
```

预期：当前所有配置工作区都会进入 Runner，新增跳过测试失败。

- [x] **步骤 3：实现触发判定**

在 `run_stop_gate_hook()` 找到配置后，按以下顺序处理：

```python
mode = read_phase(workspace)
if consume_phase(workspace, "init"):
    return 0
if mode == "planning":
    return 0
detected_changed_files = derive_changed_files(workspace)
changed_files = detected_changed_files or []
if mode != "implementation" and detected_changed_files == []:
    return 0
```

仅在继续时复用现有指纹、缓存、Runner 和 block 决策路径。

- [x] **步骤 4：运行 Stop Hook 测试**

```powershell
python -m pytest tests/stop_gate/test_hook_cli.py tests/stop_gate/test_harness_integration.py -q
```

预期：阶段触发与原有 fail-closed 测试全部通过。

### 任务 3：接入 CLI、init 和 Claude skill

**文件：**

- 修改：`entrix/cli.py`
- 修改：`tests/test_cli.py`
- 修改：`skills/entrix/SKILL.md`

- [x] **步骤 1：编写失败测试**

验证 `entrix phase planning --repo PATH` 写入规划状态，`entrix phase implementation --repo PATH` 写入实现状态；`cmd_init()` 写入一次性 `init` 状态；阶段命令不触发任何 Runner。

- [x] **步骤 2：运行测试确认失败**

```powershell
python -m pytest tests/test_cli.py -k 'phase or init' -q
```

预期：解析器不认识 `phase`，且 init 没有阶段标记。

- [x] **步骤 3：实现 CLI 接入**

增加 `cmd_phase()` 和顶层 `phase` 子命令，模式只允许 `planning`、`implementation`；`cmd_init()` 在成功写入两个配置文件后调用 `write_phase(target, "init", one_shot=True)`。

更新 skill：规划开始运行 `entrix phase planning --repo .`；用户批准开发后运行 `entrix phase implementation --repo .`；初始化仍等待用户确认。

- [x] **步骤 4：运行 CLI 测试和帮助检查**

```powershell
python -m pytest tests/test_cli.py -k 'phase or init' -q
python -m entrix phase --help
```

预期：测试通过，帮助显示两个阶段模式。

### 任务 4：文档与完整验证

**文件：**

- 修改：`README.md`
- 修改：`docs/stop-gate-usage.md`

- [x] **步骤 1：补充阶段语义**

说明头脑风暴不触发 Stop Gate，实现阶段触发；说明无阶段标记时“有变更则运行”的兼容行为；说明阶段标记是运行时状态，不是 YAML 永久豁免。

- [x] **步骤 2：运行受影响测试集**

```powershell
python -m pytest tests/stop_gate tests/test_cli.py tests/test_cli_hints.py -q
```

预期：全部通过。

- [x] **步骤 3：运行静态检查和配置校验**

```powershell
ruff check entrix/stop_gate/phase.py entrix/stop_gate/hook.py entrix/cli.py tests/stop_gate tests/test_cli.py
mypy entrix/stop_gate/phase.py entrix/stop_gate/hook.py entrix/cli.py
python -m entrix harness validate harness.yaml
git diff --check
```

预期：变更范围内无 Ruff/Mypy 错误，Harness 配置有效，差异无空白错误。
