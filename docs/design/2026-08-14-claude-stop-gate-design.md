# Claude Stop Gate 闭环系统设计文档

**文档版本:** 1.0  
**创建日期:** 2026-08-14  
**作者:** AI Architect  
**状态:** 设计完成，待实施

---

## 文档概述

本文档定义了 Entrix 项目中 Claude Stop Gate 闭环系统的完整架构设计。该系统旨在在 Claude 尝试结束任务时，自动触发独立的质量检查闭环，确保只有通过所有质量门禁的代码才能完成任务。

### 设计目标

- **自动化质量门禁** - Claude 请求结束时自动执行质量检查
- **独立证据收集** - 通过独立的 Harness 收集可复核证据  
- **智能裁决机制** - 基于证据和策略做出 PASS/FAIL/BLOCKED 裁决
- **用户友好反馈** - 提供可执行的失败反馈，指导 Claude 继续修改
- **完整闭环** - FAIL → 修改 → 重试 → PASS 的自动循环

### 技术选择

- **集成方式:** Claude Code 插件 + MCP
- **状态管理:** 混合存储（内存热状态 + 文件冷状态）
- **驱动模式:** 事件驱动（利用插件生命周期钩子）
- **输出格式:** 混合格式（Markdown 用户可读 + JSON 机器解析）

---

## 1. 系统架构设计

### 1.1 核心架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude Code 插件运行时                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Stop Gate Adapter (新增)                 │  │
│  │  • on_before_stop(session_id, task_context)          │  │
│  │  • 创建 GateAttempt                                  │  │
│  │  • 调用 StopGateEngine                               │  │
│  └─────────────────┬────────────────────────────────────┘  │
│                    │ 同步调用                               │
│  ┌─────────────────▼────────────────────────────────────┐  │
│  │              Stop Gate Engine (新增核心)               │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Session State Manager (状态管理)             │  │  │
│  │  │  • 内存: active_attempts {}                    │  │  │
│  │  │  • 文件: .claude/stop-gate/state.json          │  │  │
│  │  └─────────────────┬──────────────────────────────┘  │  │
│  │  ┌─────────────────▼──────────────────────────────┐  │  │
│  │  │  Evidence Collector (证据收集)               │  │  │
│  │  │  • 调用 Entrix fitness runner                  │  │  │
│  │  │  • 调用 review-trigger                         │  │  │
│  │  │  • 收集 artifact 和日志                        │  │  │
│  │  └─────────────────┬──────────────────────────────┘  │  │
│  │  ┌─────────────────▼──────────────────────────────┐  │  │
│  │  │  Gate Arbiter (裁决器)                         │  │  │
│  │  │  • 评估 evidence pack                          │  │  │
│  │  │  • 输出 PASS/FAIL/BLOCKED                      │  │  │
│  │  └─────────────────┬──────────────────────────────┘  │  │
│  │  ┌─────────────────▼──────────────────────────────┐  │  │
│  │  │  Feedback Formatter (反馈格式化)             │  │  │
│  │  │  • 生成可执行的失败反馈                       │  │  │
│  │  │  • 转换为 Claude 工具调用格式                  │  │  │
│  │  └───────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
│                    │ 返回裁决结果                           │
│  ┌─────────────────▼────────────────────────────────────┐  │
│  │              Claude Runtime 决策                      │  │
│  │  PASS → 允许 stop                                    │  │
│  │  FAIL/BLOCKED → 恢复工作状态 + 显示反馈               │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

                     ┌──────────────────────┐
                     │  Entrix 核心组件     │
                     │  (现有，复用)         │
                     │  • fitness runner    │
                     │  • evidence loader   │
                     │  • review trigger    │
                     │  • scoring engine    │
                     └──────────────────────┘
```

### 1.2 组件职责边界

| 组件 | 职责 | 依赖 | 边界约束 |
|------|------|------|----------|
| **Stop Gate Adapter** | 接入插件生命周期，创建 `attempt_id` | 插件 API | 不做任何裁决，只负责桥接 |
| **Session State Manager** | 管理会话状态，持久化 attempt 历史 | 文件系统 + 内存 | 不负责业务逻辑，纯状态管理 |
| **Evidence Collector** | 调用 Entrix 收集证据，组装 evidence pack | Entrix core | 独立执行，不受 Claude 影响 |
| **Gate Arbiter** | 基于证据和策略做最终裁决 | evidence pack schema | 不执行检查，只评估 |
| **Feedback Formatter** | 将裁决结果转换为 Claude 可执行格式 | Arbiter 输出 | 不修改裁决，只格式化 |

### 1.3 设计原则

- **单一职责** - 每个组件职责清晰，可独立测试
- **依赖倒置** - 高层模块不依赖低层实现细节
- **状态隔离** - 状态管理与业务逻辑分离
- **可观测性** - 每步都有日志和 artifact 产出
- **安全失败** - 异常情况下倾向于拒绝 Stop

---

## 2. 数据流设计

### 2.1 Stop 事件处理完整流程

#### 正常 PASS 流程

```
T0: Claude 工作中... (状态: WORKING)

T1: Claude 调用 stop 工具/命令
   ↓ Stop Gate Adapter.on_before_stop()
   ↓ 生成 attempt_id = UUID
   ↓ 创建 GateAttempt {
       attempt_id: "uuid-v1",
       session_id: "session-123", 
       task_id: "task-abc",
       workspace: "/path/to/repo",
       base_ref: "HEAD~1",
       changed_files: ["src/main.py"],
       requested_at: "2026-08-14T10:30:00Z"
     }

T2: Session State Manager 记录 attempt
   ↓ 内存: active_attempts[attempt_id] = REQUESTED
   ↓ 文件: .claude/stop-gate/state.json

T3: Evidence Collector 收集证据
   ├─> Entrix fitness runner
   │   └─> entrix run --tier normal --output report.json
   │       ↓ 生成 FitnessReport
   ├─> review-trigger  
   │   └─> entrix review-trigger --base HEAD~1 --json
   │       ↓ 生成 ReviewTriggerReport
   └─> 环境证据收集
       └─> Git revision, workspace fingerprint

T4: 组装 Evidence Pack
   ↓ EvidencePack {
       attempt_id: "uuid-v1",
       fitness: { status: "pass", final_score: 85, ... },
       review_trigger: { status: "pass", ... },
       collection_errors: []
     }

T5: Gate Arbiter 裁决
   ↓ 评估策略检查
   ↓ 最终裁决: Verdict { verdict: "PASS", ... }

T6: Session State Manager 更新状态
   ↓ 内存: active_attempts[attempt_id] = PASSED
   ↓ 文件: .claude/stop-gate/state.json

T7: Feedback Formatter 格式化
   ↓ 生成用户可读的成功反馈

T8: Claude Runtime 收到 PASS
   ↓ 允许任务结束 ✅
```

#### FAIL 流程

```
T5: Gate Arbiter 裁决为 FAIL
   ↓ 发现: fitness.hard_gate_blocked == true
   ↓ 裁决: Verdict {
       verdict: "FAIL",
       reason: "2 个质量门禁未通过",
       findings: [...]
     }

T6-T7: FAIL 反馈格式化
   ↓ 生成结构化反馈 {
       verdict: "FAIL",
       summary: "❌ 2 个质量门禁未通过",
       findings: [具体失败项],
       next_action: "修复问题后再次请求 stop"
     }

T8: Claude Runtime 收到 FAIL
   ↓ 拦截 stop 请求
   ↓ 显示失败反馈
   ↓ 恢复工作状态 (继续修改) 🔧

T9: Claude 修复后再次 stop
   ↓ 新 attempt_id = uuid-v2  
   ↓ 重新执行完整流程
   ↓ 最终 PASS ✅
```

### 2.2 核心数据结构

```python
@dataclass
class GateAttempt:
    """Stop 请求的完整上下文"""
    attempt_id: str
    session_id: str  
    task_id: str
    workspace: Path
    base_ref: str | None
    changed_files: list[str]
    requested_at: datetime
    stop_reason: str

@dataclass  
class EvidencePack:
    """证据集合 - 不可变"""
    schema_version: str
    attempt_id: str
    collected_at: datetime
    revision: str
    workspace_fingerprint: str
    
    fitness: FitnessEvidence
    review_trigger: ReviewTriggerEvidence
    collection_errors: list[CollectionError]
    collection_duration_seconds: float

@dataclass
class Verdict:
    """最终裁决"""
    attempt_id: str
    verdict: Literal["PASS", "FAIL", "BLOCKED"]
    decided_at: datetime
    reason: str
    summary: str
    findings: list[Finding] | None = None
```

### 2.3 输出格式策略

采用混合格式策略，兼顾用户体验和系统集成：

**格式分层:**
- **内部通信** - Python 原生对象（高性能，类型安全）
- **持久化** - JSON（兼容性，可读性）
- **用户输出** - Markdown + 结构化 JSON

**用户输出示例:**
```
❌ 质量门禁检查失败 - 不能结束任务

失败详情:
1. [硬门禁] pytest_pass - 测试命令退出码为 1
   📁 详情: /tmp/fitness-report-uuid-v1.json
   🔧 失败测试: tests/test_api.py::test_user_auth

✅ 修复建议:
• 修复失败的测试用例
• 检查代码质量问题以提升分数

🔄 下一步: 修复问题后再次请求 stop
```

---

## 3. 状态管理设计

### 3.1 双层状态管理架构

```
┌─────────────────────────────────────────────────────────────┐
│                   双层状态管理架构                            │
├─────────────────────────────────────────────────────────────┤
│  内存层 (Hot State)     │ 文件层 (Cold State)                │
│  ┌──────────────────┐  │  ┌──────────────────────────────┐   │
│  │  Active Attempts │  │  │  .claude/stop-gate/          │   │  
│  │  • 当前进行中     │  │  │    ├─ state.json             │   │
│  │  • 快速访问       │  │  │    ├─ attempts/              │   │
│  │  • 会话生命周期   │  │  │    │   ├─ {attempt_id}.json  │   │
│  └──────────────────┘  │  │    └─ history/              │   │
│         ↓ 同步          │  └──────────────────────────────┘   │
│         ↑ 恢复          │                                        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 内存状态结构

```python
class SessionStateManager:
    """管理当前会话的活跃状态"""
    
    def __init__(self):
        self.active_attempts: dict[str, AttemptState] = {}
        self.session_stats: SessionStats = SessionStats(
            session_id=self._generate_session_id(),
            started_at=datetime.now(timezone.utc),
            total_attempts=0,
            passed_attempts=0,
            failed_attempts=0
        )
    
    def create_attempt(self, attempt: GateAttempt) -> str:
        """创建新的停止尝试并同步到文件"""
        
    def update_attempt_status(self, attempt_id: str, status: AttemptStatus):
        """更新尝试状态并同步"""
        
    def cleanup_expired_attempts(self, max_age_hours: int = 24):
        """清理过期状态"""

@dataclass
class AttemptState:
    attempt_id: str
    status: AttemptStatus  # REQUESTED → COLLECTING → ARBITRATING → PASSED/FAILED/BLOCKED
    created_at: datetime
    updated_at: datetime | None = None
    attempt_data: GateAttempt | None = None
    verdict: Verdict | None = None
    evidence_pack_path: Path | None = None
```

### 3.3 文件系统布局

```
.claude/stop-gate/
├─ state.json                    # 当前活跃状态 (经常更新)
├─ state.backup.json             # 备份状态 (容错恢复)
├─ attempts/                      # 完整attempt历史
│  ├─ 2026-08-14/
│  │  ├─ uuid-v1.json            # 按日期分组织
│  │  └─ uuid-v2.json
├─ evidence/                       # 证据包存档
│  ├─ uuid-v1.json
│  └─ uuid-v2.json  
├─ feedback/                      # 用户反馈存档
│  ├─ uuid-v1.md                 # Markdown格式
│  └─ uuid-v2.md
└─ history/                       # 压缩的历史日志
   └─ 2026-08/
```

### 3.4 状态同步和恢复

**同步策略:**
- **关键操作** - 立即持久化（attempt 创建、状态变更）
- **批量操作** - 定期批量持久化（统计数据）
- **原子写入** - 先写临时文件，再重命名

**恢复机制:**
1. 启动时从 `state.json` 恢复活跃状态
2. 如果主文件损坏，从 `state.backup.json` 恢复
3. 清理过期状态（24小时）
4. 验证状态一致性

---

## 4. 错误处理设计

### 4.1 错误处理分层

```
系统级错误        → BLOCKED + 升级到用户
执行级错误        → FAIL + 重试机制  
可恢复错误        → 重试 + 降级
用户级错误        → 明确指导
```

### 4.2 错误类型定义

```python
class StopGateError(Exception):
    """Stop Gate 错误基类"""
    def __init__(self, message: str, recoverable: bool = True):
        self.message = message
        self.recoverable = recoverable

class SystemError(StopGateError):
    """系统级错误 - 阻塞所有操作"""
    recoverable = False

class ExecutionError(StopGateError):
    """执行级错误 - 导致 FAIL 或 BLOCKED"""
    
class RecoverableError(StopGateError):
    """可恢复错误 - 自动重试"""
    recoverable = True
```

### 4.3 容错策略矩阵

| 错误类型 | 默认行为 | 降级策略 | 用户通知 |
|---------|---------|---------|----------|
| Fitness 检查失败 | FAIL | 允许重试 | 显示失败项 |
| Evidence 收集失败 | BLOCKED | 提示手动检查 | 明确错误原因 |
| 检查超时 (>5min) | BLOCKED | 建议分 tier 执行 | 超时指导 |
| 状态文件损坏 | BLOCKED | 尝试备份恢复 | 恢复指导 |
| Entrix 未安装 | BLOCKED | 安装指导 | 安装文档 |

### 4.4 优雅降级策略

**关键降级场景:**

1. **Entrix 不可用** - BLOCKED + 安装指导
2. **部分证据缺失** - BLOCKED + 手动检查建议
3. **检查超时** - FAIL + 优化建议
4. **状态文件损坏** - 尝试恢复 + 继续运行

### 4.5 错误日志和监控

```python
class ErrorLogger:
    """结构化错误日志"""
    
    def log_error(self, error: StopGateError, context: dict):
        """记录错误到 .claude/stop-gate/errors.logl"""
        
    def get_error_summary(self, hours: int = 24) -> dict:
        """获取错误统计摘要"""
```

---

## 5. 接口和 API 设计

### 5.1 Stop Gate Adapter API

```python
class StopGateAdapter:
    """Claude Code 插件集成接口"""
    
    def on_before_stop(self, session_context: dict) -> StopDecision:
        """拦截 Claude stop 请求
        
        Args:
            session_context: {
                "session_id": str,
                "task_id": str, 
                "workspace": Path,
                "changed_files": list[str],
                "stop_reason": str
            }
        
        Returns:
            StopDecision {
                "allow_stop": bool,
                "feedback": str,
                "attempt_id": str
            }
        """
```

### 5.2 Stop Gate Engine API

```python
class StopGateEngine:
    """核心 Stop Gate 执行引擎"""
    
    def process_stop_request(self, attempt: GateAttempt) -> Verdict:
        """处理 Stop 请求，返回裁决"""
        
    def get_attempt_history(self, session_id: str) -> list[AttemptState]:
        """获取会话历史"""
        
    def cleanup(self, max_age_hours: int = 24):
        """清理过期状态"""
```

### 5.3 MCP 集成 API

```python
@mcp.tool()
def stop_gate_check(
    session_id: str,
    task_id: str,
    workspace: str,
    changed_files: list[str]
) -> dict:
    """MCP 工具：执行 Stop Gate 检查
    
    Returns:
        {
            "attempt_id": str,
            "verdict": "PASS|FAIL|BLOCKED", 
            "feedback": str,
            "evidence_path": str
        }
    """
```

---

## 6. 实施考虑

### 6.1 优先级分级

**P0 - 最小可用版本:**
- ✅ Stop Gate Adapter 实现
- ✅ Session State Manager 
- ✅ Evidence Collector
- ✅ Gate Arbiter (基础策略)
- ✅ Feedback Formatter
- ✅ 基础错误处理

**P1 - 可靠性和可运维性:**
- ✅ 完整的错误处理
- ✅ 状态恢复机制
- ✅ 错误日志和监控
- ✅ 并发控制
- ✅ 性能优化

**P2 - 高级功能:**
- ✅ 证据压缩和归档
- ✅ 统计分析和报告
- ✅ MCP 双向通信
- ✅ 高级裁决策略

### 6.2 集成依赖

**必需组件:**
- Claude Code 插件 API (假设支持生命周期钩子)
- Entrix 核心 (现有，复用)
- Python 3.10+
- 文件系统访问权限

**可选组件:**
- MCP 服务 (用于集成增强)
- 监控系统 (用于运维)

### 6.3 测试策略

**单元测试:**
- 每个组件独立测试
- 模拟外部依赖
- 边界条件覆盖

**集成测试:**
- 完整流程测试
- 错误场景模拟
- 性能测试

**端到端测试:**
- PASS 场景
- FAIL → 修复 → PASS 场景
- BLOCKED 场景
- 异常恢复场景

---

## 7. 验收标准

系统必须满足以下所有条件才能宣称完成：

### 7.1 功能验收

1. ✅ **自动拦截** - Claude 请求 stop 时自动执行检查
2. ✅ **独立执行** - 证据收集独立于 Claude 进程
3. ✅ **准确裁决** - 基于证据做出正确的 PASS/FAIL/BLOCKED
4. ✅ **完整反馈** - FAIL 反馈包含具体失败项和修复建议
5. ✅ **重试机制** - 支持多次 stop 尝试，每次重新收集证据
6. ✅ **状态持久化** - 系统重启后能恢复状态

### 7.2 质量验收

1. ✅ **性能要求** - 完整检查在 5 分钟内完成
2. ✅ **可靠性要求** - 错误情况下安全失败，从不伪造 PASS
3. ✅ **可观测性** - 每步都有日志和 artifact
4. ✅ **容错性** - 任意组件失败不影响整体一致性

### 7.3 用户体验验收

1. ✅ **反馈清晰** - 用户能理解失败原因和修复步骤
2. ✅ **响应及时** - 不让用户等待过久
3. ✅ **状态可见** - 用户能查看当前检查状态和历史

---

## 8. 风险和限制

### 8.1 已知风险

| 风险 | 影响 | 缓解策略 |
|------|------|----------|
| Claude 插件 API 限制 | 高 | 提前验证 API 能力，设计备选方案 |
| 状态文件损坏 | 中 | 双重备份 + 恢复机制 |
| 性能瓶颈 | 中 | 并行执行，分级检查 |
| 误判率 | 低 | 多层验证，人工复核入口 |

### 8.2 设计限制

- **不支持跨会话状态** - 每个会话独立管理
- **不支持分布式** - 单机部署，无集群支持
- **依赖文件系统** - 需要稳定的磁盘 I/O
- **假设 Claude 插件能力** - 依赖特定 API 支持

### 8.3 非目标

本设计不包含以下功能：
- ❌ 自动修改业务代码
- ❌ 需求语义验证（只验证技术质量）
- ❌ 跨项目状态共享
- ❌ 高可用集群部署

---

## 9. 未来扩展方向

### 9.1 短期改进 (P2)

- MCP 双向通信增强
- 证据压缩和长期归档  
- 统计分析和可视化
- 高级裁决策略配置

### 9.2 长期愿景

- 分布式状态管理
- 机器学习辅助裁决
- 跨项目质量趋势分析
- 企业级部署支持

---

## 附录 A：术语表

| 术语 | 定义 |
|------|------|
| **Attempt** | 一次 stop 请求的完整处理过程 |
| **Evidence Pack** | 不可变的证据集合，包含所有检查结果 |
| **Gate Arbiter** | 基于证据和策略做出最终裁决的组件 |
| **Harness** | 独立执行检查的系统，不受 AI 影响 |
| **Stop Gate** | 拦截 stop 请求并执行质量检查的机制 |
| **Verdict** | 最终裁决结果：PASS/FAIL/BLOCKED |

---

## 附录 B：参考文档

- `docs/agent-stop-gate-implementation-status.md` - 实施状态跟踪
- `docs/adr/` - 架构决策记录
- `docs/fitness/` - 质量规格定义

---

**文档状态:** 设计完成  
**下一步:** 编写实现计划，调用 `writing-plans` 技能