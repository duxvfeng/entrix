# Claude Stop Gate 使用指南

## 快速开始

### 1. 基本使用

```python
from entrix.stop_gate import StopGateAdapter
from pathlib import Path

# 创建适配器
adapter = StopGateAdapter()

# 在 Claude Code 插件中调用
session_context = {
    "session_id": "current-session",
    "task_id": "current-task",
    "workspace": Path.cwd(),
    "changed_files": ["src/main.py", "tests/test_main.py"],
    "stop_reason": "agent_completed"
}

decision = adapter.on_before_stop(session_context)

if decision.allow_stop:
    print("✅ 质量检查通过，可以结束任务")
else:
    print(f"❌ {decision.feedback}")
    # 继续修复问题...
```

### 2. 配置质量门禁

在项目根目录创建 `docs/fitness/code-quality.md`：

```yaml
---
dimension: code_quality
weight: 35
threshold:
  pass: 90
  warn: 80
metrics:
  - name: ruff_pass
    command: ruff check . 2>&1
    hard_gate: true
    tier: fast
    description: "Ruff must pass with no lint errors"
---
```

### 3. 运行和测试

```bash
# 直接测试 Stop Gate
python -m pytest tests/stop_gate/ -v

# 运行集成测试
python -m pytest tests/stop_gate/test_integration.py -v -m integration

# 在实际项目中使用
entrix run --tier normal
```

### 4. Claude Code 插件 Hook（推荐）

安装 Claude Code 插件（`/plugin install entrix@entrix`）后，Stop hook 自动生效，无需手动调用 Python API：

> marketplace 源地址：`https://gitee.com/duxvfeng/entrix/repository/archive/main.zip`
> 如果该源不被当前 Claude Code 版本支持，请改用[手动配置方式](local-plugin-install.md)。

```text
Claude 请求 Stop
  -> hooks/stop-gate.sh 调用 entrix stop-gate
  -> 读取 stdin 的 hook 载荷（session_id / cwd / stop_hook_active）
  -> 工作区无 docs/fitness/？直接放行
  -> 有规格？收集证据并裁决
       -> PASS: 退出码 0，无输出，允许停止
       -> FAIL/BLOCKED: 输出 {"decision": "block", "reason": "..."}，Claude 继续修复
```

要点：

- **激活条件**：仓库存在 `docs/fitness/*.md` 或 `docs/fitness/manifest.yaml`
- **防循环**：`stop_hook_active` 为真时立即放行（Claude Code 已因此 hook 继续工作）
- **禁用**：`export ENTRIX_STOP_GATE_DISABLED=1`
- **超时**：hook 层 295 秒；`ENTRIX_STOP_GATE_TIMEOUT` 或 `--timeout` 控制证据收集
- **查找链**：PATH 上的 `entrix` → `uvx entrix` → 插件内源码副本 → 全部失败时放行

手动验证（模拟 Claude Code 输入）：

```bash
echo "{\"session_id\": \"t\", \"cwd\": \"$PWD\"}" | entrix stop-gate
# 阻断时输出：{"decision": "block", "reason": "..."}
```

## 架构概述

Stop Gate 系统包含以下核心组件：

1. **Stop Gate Adapter** - Claude Code 插件接口
2. **Session State Manager** - 混合状态管理
3. **Evidence Collector** - 独立证据收集
4. **Gate Arbiter** - 智能裁决器
5. **Feedback Formatter** - 用户友好反馈

## 故障排除

### 常见问题

**Q: Stop Gate 不工作？**
- 确认 Entrix 正确安装：`pip install entrix`
- 检查 `docs/fitness/` 目录存在配置文件
- 查看 `.claude/stop-gate/` 中的日志

**Q: 总是 BLOCKED？**
- 检查 Git 仓库是否正确初始化
- 确认质量检查配置文件格式正确
- 查看详细错误日志

**Q: 性能慢？**
- 使用 `--tier fast` 只运行快速检查
- 调整 `timeout_seconds` 参数
- 检查是否有超时的检查项

## 组件详情

### StopGateAdapter

`StopGateAdapter` 是 Claude Code 插件的入口点。它接收会话上下文，创建 `GateAttempt`，并调用引擎处理 stop 请求。

```python
adapter = StopGateAdapter(
    state_dir=Path.cwd() / ".claude" / "stop-gate",
    timeout_seconds=300
)
```

### StopGateEngine

`StopGateEngine` 是核心编排引擎，负责：
1. 创建和管理尝试状态
2. 收集证据
3. 执行裁决
4. 格式化反馈
5. 更新最终状态

```python
from entrix.stop_gate import StopGateEngine
from entrix.stop_gate.model import GateAttempt

engine = StopGateEngine()
attempt = GateAttempt.create(
    session_id="session-1",
    task_id="task-1",
    workspace=Path.cwd(),
    changed_files=["src/main.py"],
    stop_reason="agent_completed"
)
decision = engine.process_stop_request(attempt)
```

## 裁决规则

GateArbiter 根据以下规则做出裁决：

- **PASS**: 所有检查通过，无硬门禁失败，无人工审查要求
- **FAIL**: 硬门禁失败或分数不足
- **BLOCKED**: 证据缺失或需要人工审查（严格模式下）

## 开发

### 测试

```bash
python -m pytest tests/stop_gate/ -v
```

### 代码风格

```bash
ruff check entrix/stop_gate tests/stop_gate
```
