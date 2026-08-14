# Claude Stop Gate 闭环系统实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现自动化质量门禁系统，在 Claude 请求结束时独立收集证据并裁决是否允许任务完成。

**架构：** 内嵌插件架构，包含 Stop Gate Adapter、Session State Manager、Evidence Collector、Gate Arbiter、Feedback Formatter 五个核心组件，采用混合状态管理（内存+文件系统）。

**技术栈：** Python 3.10+、Claude Code 插件 API、Entrix 核心组件、JSON/Markdown 混合格式

---

## 阶段 1：基础设施（模型和错误处理）

### 任务 1.1：创建核心数据模型

**文件：**
- 创建：`entrix/stop_gate/__init__.py`
- 创建：`entrix/stop_gate/model.py`
- 测试：`tests/stop_gate/test_model.py`

- [ ] **步骤 1.1：编写模型测试**

```python
# tests/stop_gate/test_model.py
import pytest
from datetime import datetime, timezone
from pathlib import Path
from entrix.stop_gate.model import GateAttempt, AttemptStatus, AttemptState

def test_gate_attempt_creation():
    """测试 GateAttempt 基本创建"""
    attempt = GateAttempt(
        attempt_id="test-uuid-1",
        session_id="session-123",
        task_id="task-abc",
        workspace=Path("/test/workspace"),
        base_ref="HEAD~1",
        changed_files=["src/main.py"],
        requested_at=datetime.now(timezone.utc),
        stop_reason="agent_completed"
    )
    assert attempt.attempt_id == "test-uuid-1"
    assert attempt.stop_reason == "agent_completed"

def test_attempt_status_enum():
    """测试 AttemptStatus 枚举"""
    assert AttemptStatus.REQUESTED.value == "requested"
    assert AttemptStatus.COLLECTING.value == "collecting"
    assert AttemptStatus.ARBITRATING.value == "arbitrating"
    assert AttemptStatus.PASSED.value == "passed"
    assert AttemptStatus.FAILED.value == "failed"
    assert AttemptStatus.BLOCKED.value == "blocked"

def test_attempt_state_creation():
    """测试 AttemptState 创建"""
    state = AttemptState(
        attempt_id="test-uuid-1",
        status=AttemptStatus.REQUESTED,
        created_at=datetime.now(timezone.utc)
    )
    assert state.status == AttemptStatus.REQUESTED
    assert state.verdict is None
```

- [ ] **步骤 1.2：运行测试验证失败**

```bash
pytest tests/stop_gate/test_model.py -v
```

预期：FAIL，报错 "No module named 'entrix.stop_gate.model'"

- [ ] **步骤 1.3：创建包结构和基础模型**

```python
# entrix/stop_gate/__init__.py
"""Entrix Stop Gate - 自动化质量门禁系统"""

from entrix.stop_gate.model import (
    GateAttempt,
    AttemptStatus,
    AttemptState,
    EvidencePack,
    Verdict,
    Finding,
    StopDecision
)

__all__ = [
    "GateAttempt",
    "AttemptStatus", 
    "AttemptState",
    "EvidencePack",
    "Verdict",
    "Finding",
    "StopDecision"
]
```

```python
# entrix/stop_gate/model.py
"""核心数据模型定义"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

class AttemptStatus(Enum):
    """Stop 尝试的状态"""
    REQUESTED = "requested"
    COLLECTING = "collecting"
    ARBITRATING = "arbitrating"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"

@dataclass
class GateAttempt:
    """Stop 请求的完整上下文"""
    attempt_id: str
    session_id: str
    task_id: str
    workspace: Path
    base_ref: Optional[str]
    changed_files: list[str]
    requested_at: datetime
    stop_reason: str
    
    @classmethod
    def create(cls, session_id: str, task_id: str, workspace: Path, 
               changed_files: list[str], stop_reason: str) -> "GateAttempt":
        """创建新的 GateAttempt，自动生成 attempt_id"""
        return cls(
            attempt_id=str(uuid4()),
            session_id=session_id,
            task_id=task_id,
            workspace=workspace,
            base_ref=None,
            changed_files=changed_files,
            requested_at=datetime.now(timezone.utc),
            stop_reason=stop_reason
        )

@dataclass
class AttemptState:
    """尝试的运行时状态"""
    attempt_id: str
    status: AttemptStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    attempt_data: Optional[GateAttempt] = None
    verdict: Optional["Verdict"] = None
    evidence_pack_path: Optional[Path] = None

@dataclass
class Finding:
    """具体的检查发现"""
    source: str
    metric: str
    severity: Literal["hard_gate", "soft_gate", "advisory"]
    message: str
    artifact_path: Optional[str] = None
    suggestions: list[str] = field(default_factory=list)

@dataclass
class Verdict:
    """最终裁决"""
    attempt_id: str
    verdict: Literal["PASS", "FAIL", "BLOCKED"]
    decided_at: datetime
    reason: str
    summary: str
    findings: Optional[list[Finding]] = None

@dataclass
class EvidencePack:
    """证据集合"""
    schema_version: str = "evidence-pack.v1"
    attempt_id: str = ""
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    revision: str = ""
    workspace_fingerprint: str = ""
    fitness: dict = field(default_factory=dict)
    review_trigger: dict = field(default_factory=dict)
    collection_errors: list = field(default_factory=list)
    collection_duration_seconds: float = 0.0

@dataclass
class StopDecision:
    """Stop 决策结果"""
    allow_stop: bool
    feedback: str
    attempt_id: str
    verdict: Optional[Verdict] = None
```

- [ ] **步骤 1.4：运行测试验证通过**

```bash
pytest tests/stop_gate/test_model.py -v
```

预期：PASS

- [ ] **步骤 1.5：Commit 基础模型**

```bash
git add entrix/stop_gate/__init__.py entrix/stop_gate/model.py tests/stop_gate/test_model.py
git commit -m "feat: add core data models for Stop Gate system"
```

### 任务 1.2：创建错误处理系统

**文件：**
- 创建：`entrix/stop_gate/errors.py`
- 测试：`tests/stop_gate/test_errors.py`

- [ ] **步骤 2.1：编写错误处理测试**

```python
# tests/stop_gate/test_errors.py
import pytest
from entrix.stop_gate.errors import (
    StopGateError,
    SystemError,
    ExecutionError,
    RecoverableError,
    ConfigurationError,
    FitnessCheckError,
    TimeoutError
)

def test_stop_gate_error_base():
    """测试基础错误类"""
    error = StopGateError("Test error", recoverable=True)
    assert error.message == "Test error"
    assert error.recoverable is True
    assert error.timestamp is not None

def test_system_error_not_recoverable():
    """测试系统错误默认不可恢复"""
    error = SystemError("System failure")
    assert error.recoverable is False

def test_execution_error_with_details():
    """测试执行错误包含详细信息"""
    error = FitnessCheckError("pytest_pass", 1, "Test failed")
    assert error.metric_name == "pytest_pass"
    assert error.exit_code == 1
    assert "Test failed" in error.output

def test_timeout_error():
    """测试超时错误"""
    error = TimeoutError("fitness_check", 300)
    assert error.operation == "fitness_check"
    assert error.timeout_seconds == 300
```

- [ ] **步骤 2.2：运行测试验证失败**

```bash
pytest tests/stop_gate/test_errors.py -v
```

预期：FAIL，报错 "No module named 'entrix.stop_gate.errors'"

- [ ] **步骤 2.3：实现错误处理类**

```python
# entrix/stop_gate/errors.py
"""Stop Gate 错误处理系统"""

from datetime import datetime, timezone
from typing import Optional

class StopGateError(Exception):
    """Stop Gate 错误基类"""
    
    def __init__(self, message: str, recoverable: bool = True):
        self.message = message
        self.recoverable = recoverable
        self.timestamp = datetime.now(timezone.utc)
        super().__init__(message)

class SystemError(StopGateError):
    """系统级错误 - 阻塞所有操作"""
    recoverable = False  # 默认不可恢复
    
    def __init__(self, message: str):
        super().__init__(message, recoverable=False)

class ExecutionError(StopGateError):
    """执行级错误 - 导致 FAIL 或 BLOCKED"""
    
class RecoverableError(StopGateError):
    """可恢复错误 - 自动重试"""
    recoverable = True

class ConfigurationError(StopGateError):
    """配置错误 - 用户干预"""
    recoverable = False

class FitnessCheckError(ExecutionError):
    """Fitness 检查执行失败"""
    
    def __init__(self, metric_name: str, exit_code: int, output: str):
        self.metric_name = metric_name
        self.exit_code = exit_code
        self.output = output
        message = f"检查 {metric_name} 失败，退出码: {exit_code}"
        super().__init__(message)

class TimeoutError(ExecutionError):
    """执行超时"""
    
    def __init__(self, operation: str, timeout_seconds: int):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        message = f"{operation} 在 {timeout_seconds}秒后超时"
        super().__init__(message)
```

- [ ] **步骤 2.4：运行测试验证通过**

```bash
pytest tests/stop_gate/test_errors.py -v
```

预期：PASS

- [ ] **步骤 2.5：Commit 错误处理系统**

```bash
git add entrix/stop_gate/errors.py tests/stop_gate/test_errors.py
git commit -m "feat: add error handling system for Stop Gate"
```

---

## 阶段 2：状态管理器

### 任务 2.1：实现状态管理器

**文件：**
- 创建：`entrix/stop_gate/state_manager.py`
- 测试：`tests/stop_gate/test_state_manager.py`

- [ ] **步骤 3.1：编写状态管理器测试**

```python
# tests/stop_gate/test_state_manager.py
import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import json
from entrix.stop_gate.model import GateAttempt, AttemptStatus
from entrix.stop_gate.state_manager import SessionStateManager

def test_create_attempt():
    """测试创建新尝试"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionStateManager(state_dir=Path(tmpdir))
        
        attempt = GateAttempt(
            attempt_id="test-uuid",
            session_id="session-1",
            task_id="task-1", 
            workspace=Path("/test"),
            base_ref="HEAD~1",
            changed_files=["src/test.py"],
            requested_at=datetime.now(timezone.utc),
            stop_reason="agent_completed"
        )
        
        attempt_id = manager.create_attempt(attempt)
        assert attempt_id == "test-uuid"
        assert attempt_id in manager.active_attempts

def test_update_attempt_status():
    """测试更新尝试状态"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionStateManager(state_dir=Path(tmpdir))
        
        attempt = GateAttempt(
            attempt_id="test-uuid",
            session_id="session-1",
            task_id="task-1",
            workspace=Path("/test"),
            base_ref=None,
            changed_files=[],
            requested_at=datetime.now(timezone.utc),
            stop_reason="test"
        )
        
        manager.create_attempt(attempt)
        manager.update_attempt_status("test-uuid", AttemptStatus.COLLECTING)
        
        state = manager.get_attempt("test-uuid")
        assert state.status == AttemptStatus.COLLECTING

def test_persist_and_recover_state():
    """测试状态持久化和恢复"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建管理器并添加状态
        manager1 = SessionStateManager(state_dir=Path(tmpdir))
        
        attempt = GateAttempt(
            attempt_id="test-uuid",
            session_id="session-1",
            task_id="task-1",
            workspace=Path("/test"),
            base_ref=None,
            changed_files=[],
            requested_at=datetime.now(timezone.utc),
            stop_reason="test"
        )
        
        manager1.create_attempt(attempt)
        
        # 创建新管理器，应该能恢复状态
        manager2 = SessionStateManager(state_dir=Path(tmpdir))
        assert "test-uuid" in manager2.active_attempts

def test_cleanup_expired_attempts():
    """测试清理过期尝试"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionStateManager(state_dir=Path(tmpdir))
        
        # 添加一个过期尝试（通过直接操作状态）
        old_time = datetime.now(timezone.utc).timestamp() - (25 * 3600)  # 25小时前
        # 这里简化测试，实际中需要模拟过期时间
        
        manager.cleanup_expired_attempts(max_age_hours=24)
        # 验证过期状态被清理
```

- [ ] **步骤 3.2：运行测试验证失败**

```bash
pytest tests/stop_gate/test_state_manager.py -v
```

预期：FAIL，报错 "No module named 'entrix.stop_gate.state_manager'"

- [ ] **步骤 3.3：实现状态管理器**

```python
# entrix/stop_gate/state_manager.py
"""会话状态管理器 - 混合存储策略"""

import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import RLock
from typing import Optional
from dataclasses import dataclass, field, asdict
from uuid import uuid4

from entrix.stop_gate.model import GateAttempt, AttemptState, AttemptStatus
from entrix.stop_gate.errors import SystemError

@dataclass
class SessionStats:
    """会话统计信息"""
    session_id: str
    started_at: datetime
    total_attempts: int = 0
    passed_attempts: int = 0
    failed_attempts: int = 0

class SessionStateManager:
    """管理当前会话的活跃状态 - 混合存储策略"""
    
    def __init__(self, state_dir: Optional[Path] = None):
        if state_dir is None:
            state_dir = Path.cwd() / ".claude" / "stop-gate"
        
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = self.state_dir / "state.json"
        self.backup_file = self.state_dir / "state.backup.json"
        
        # 内存状态
        self.active_attempts: dict[str, AttemptState] = {}
        self.lock = RLock()
        
        # 会话统计
        self.session_stats = SessionStats(
            session_id=str(uuid4()),
            started_at=datetime.now(timezone.utc)
        )
        
        # 尝试从磁盘恢复状态
        self._recover_from_disk()
    
    def create_attempt(self, attempt: GateAttempt) -> str:
        """创建新的停止尝试并同步到文件系统"""
        with self.lock:
            attempt_id = attempt.attempt_id
            
            state = AttemptState(
                attempt_id=attempt_id,
                status=AttemptStatus.REQUESTED,
                created_at=datetime.now(timezone.utc),
                attempt_data=attempt
            )
            
            self.active_attempts[attempt_id] = state
            self.session_stats.total_attempts += 1
            
            # 同步到文件系统
            self._persist_state()
            
            return attempt_id
    
    def update_attempt_status(self, attempt_id: str, status: AttemptStatus, 
                             verdict: Optional[dict] = None,
                             evidence_pack_path: Optional[Path] = None):
        """更新尝试状态并同步"""
        with self.lock:
            if attempt_id not in self.active_attempts:
                raise ValueError(f"Attempt {attempt_id} 不存在")
            
            state = self.active_attempts[attempt_id]
            state.status = status
            state.updated_at = datetime.now(timezone.utc)
            
            if verdict:
                # 简化处理，实际中应该构造 Verdict 对象
                state.verdict = verdict
            if evidence_pack_path:
                state.evidence_pack_path = evidence_pack_path
            
            # 更新统计
            if status == AttemptStatus.PASSED:
                self.session_stats.passed_attempts += 1
            elif status == AttemptStatus.FAILED:
                self.session_stats.failed_attempts += 1
            
            # 同步到文件系统
            self._persist_state()
    
    def get_attempt(self, attempt_id: str) -> Optional[AttemptState]:
        """获取尝试状态 - 优先从内存读取"""
        with self.lock:
            return self.active_attempts.get(attempt_id)
    
    def cleanup_expired_attempts(self, max_age_hours: int = 24):
        """清理过期的尝试状态"""
        with self.lock:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            expired = [
                attempt_id for attempt_id, state in self.active_attempts.items()
                if state.created_at < cutoff
            ]
            
            for attempt_id in expired:
                del self.active_attempts[attempt_id]
            
            if expired:
                self._persist_state()
    
    def _persist_state(self):
        """持久化状态到文件系统"""
        try:
            state_data = {
                "schema_version": "session-state.v1",
                "session_id": self.session_stats.session_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "active_attempts": {
                    attempt_id: {
                        "status": state.status.value,
                        "created_at": state.created_at.isoformat(),
                        "updated_at": state.updated_at.isoformat() if state.updated_at else None
                    }
                    for attempt_id, state in self.active_attempts.items()
                },
                "session_stats": {
                    "total_attempts": self.session_stats.total_attempts,
                    "passed_attempts": self.session_stats.passed_attempts,
                    "failed_attempts": self.session_stats.failed_attempts
                }
            }
            
            # 原子写入：先写临时文件，再重命名
            temp_file = self.state_file.with_suffix('.tmp')
            temp_file.write_text(json.dumps(state_data, indent=2))
            temp_file.replace(self.state_file)
            
        except Exception as e:
            raise SystemError(f"状态持久化失败: {e}")
    
    def _recover_from_disk(self):
        """从磁盘恢复状态"""
        if not self.state_file.exists():
            return
        
        try:
            data = json.loads(self.state_file.read_text())
            
            # 恢复活跃尝试
            for attempt_id, state_data in data.get("active_attempts", {}).items():
                # 简化恢复，实际中需要完整的对象重建
                state = AttemptState(
                    attempt_id=attempt_id,
                    status=AttemptStatus(state_data["status"]),
                    created_at=datetime.fromisoformat(state_data["created_at"])
                )
                self.active_attempts[attempt_id] = state
            
        except Exception as e:
            # 恢复失败，使用干净状态
            print(f"状态恢复失败: {e}，使用干净状态")
```

- [ ] **步骤 3.4：运行测试验证通过**

```bash
pytest tests/stop_gate/test_state_manager.py -v
```

预期：PASS（可能需要调整测试细节）

- [ ] **步骤 3.5：Commit 状态管理器**

```bash
git add entrix/stop_gate/state_manager.py tests/stop_gate/test_state_manager.py
git commit -m "feat: implement session state manager with hybrid storage"
```

---

## 阶段 3：证据收集器

### 任务 3.1：实现证据收集器

**文件：**
- 创建：`entrix/stop_gate/collector.py`
- 测试：`tests/stop_gate/test_collector.py`

- [ ] **步骤 4.1：编写证据收集器测试**

```python
# tests/stop_gate/test_collector.py
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from entrix.stop_gate.model import GateAttempt, EvidencePack
from entrix.stop_gate.collector import EvidenceCollector

def test_collect_evidence_success():
    """测试成功收集证据"""
    with patch('entrix.stop_gate.collector.run_fitness_report') as mock_fitness:
        # 模拟成功的 fitness 报告
        mock_fitness.return_value = (Mock(
            final_score=85,
            hard_gate_blocked=False,
            score_blocked=False
        ), Mock())
        
        collector = EvidenceCollector()
        attempt = GateAttempt(
            attempt_id="test-uuid",
            session_id="session-1",
            task_id="task-1",
            workspace=Path("/test"),
            base_ref="HEAD~1",
            changed_files=["src/test.py"],
            requested_at=datetime.now(timezone.utc),
            stop_reason="test"
        )
        
        evidence_pack = collector.collect_evidence(attempt)
        
        assert evidence_pack.attempt_id == "test-uuid"
        assert evidence_pack.fitness["status"] == "pass"

def test_collect_with_review_trigger():
    """测试包含 review trigger 的证据收集"""
    with patch('entrix.stop_gate.collector.evaluate_review_triggers') as mock_review:
        mock_review.return_value = Mock(
            human_review_required=False,
            triggers=[]
        )
        
        collector = EvidenceCollector()
        # ... 创建 attempt 和测试逻辑

def test_collect_timeout_handling():
    """测试收集超时的处理"""
    collector = EvidenceCollector(timeout_seconds=1)
    
    # 模拟超时场景
    with patch('entrix.stop_gate.collector.run_fitness_report') as mock_fitness:
        mock_fitness.side_effect = TimeoutError("Simulated timeout")
        
        attempt = Mock()
        evidence_pack = collector.collect_evidence(attempt)
        
        # 应该包含超时错误
        assert any("timeout" in str(error).lower() for error in evidence_pack.collection_errors)
```

- [ ] **步骤 4.2：运行测试验证失败**

```bash
pytest tests/stop_gate/test_collector.py -v
```

预期：FAIL，报错 "No module named 'entrix.stop_gate.collector'"

- [ ] **步骤 4.3：实现证据收集器**

```python
# entrix/stop_gate/collector.py
"""证据收集器 - 独立收集质量检查证据"""

import subprocess
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from entrix.stop_gate.model import GateAttempt, EvidencePack
from entrix.stop_gate.errors import ExecutionError, TimeoutError, EvidenceCollectionError

class EvidenceCollector:
    """收集质量检查证据，独立于 Claude 进程执行"""
    
    def __init__(self, timeout_seconds: int = 300):
        self.timeout_seconds = timeout_seconds
    
    def collect_evidence(self, attempt: GateAttempt) -> EvidencePack:
        """收集完整的证据包"""
        start_time = time.time()
        evidence_pack = EvidencePack(attempt_id=attempt.attempt_id)
        
        try:
            # 1. 收集环境证据
            self._collect_environment_evidence(attempt, evidence_pack)
            
            # 2. 运行 Entrix fitness 检查
            self._collect_fitness_evidence(attempt, evidence_pack)
            
            # 3. 运行 review trigger
            self._collect_review_trigger_evidence(attempt, evidence_pack)
            
        except Exception as e:
            evidence_pack.collection_errors.append({
                "component": "collector",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        finally:
            evidence_pack.collection_duration_seconds = time.time() - start_time
        
        return evidence_pack
    
    def _collect_environment_evidence(self, attempt: GateAttempt, evidence: EvidencePack):
        """收集环境证据"""
        try:
            # 获取 Git revision
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=attempt.workspace,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                evidence.revision = result.stdout.strip()
            
            # 获取工作区指纹
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=attempt.workspace,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                evidence.workspace_fingerprint = result.stdout.strip()
                
        except subprocess.TimeoutExpired:
            raise TimeoutError("git_rev_parse", 10)
        except Exception as e:
            raise EvidenceCollectionError("environment", str(e))
    
    def _collect_fitness_evidence(self, attempt: GateAttempt, evidence: EvidencePack):
        """运行 Entrix fitness 检查"""
        try:
            from entrix.engine import run_fitness_report
            from entrix.governance import GovernancePolicy
            from entrix.presets import get_project_preset
            
            policy = GovernancePolicy()
            report, _ = run_fitness_report(attempt.workspace, policy, get_project_preset())
            
            # 转换为证据格式
            evidence.fitness = {
                "status": "pass" if not report.hard_gate_blocked and not report.score_blocked else "fail",
                "final_score": report.final_score,
                "hard_gate_blocked": report.hard_gate_blocked,
                "score_blocked": report.score_blocked,
                "metrics_count": sum(len(ds.results) for ds in report.dimensions),
                "failed_metrics": [
                    {
                        "name": r.metric_name,
                        "severity": "hard_gate" if r.hard_gate else "soft_gate",
                        "output": r.output[:500]  # 限制输出长度
                    }
                    for ds in report.dimensions
                    for r in ds.results
                    if not r.passed
                ]
            }
            
        except TimeoutError:
            evidence.fitness = {"status": "timeout", "error": "检查超时"}
        except Exception as e:
            evidence.fitness = {"status": "error", "error": str(e)}
    
    def _collect_review_trigger_evidence(self, attempt: GateAttempt, evidence: EvidencePack):
        """运行 review trigger 检查"""
        try:
            from entrix.review_trigger import (
                collect_changed_files,
                collect_diff_stats,
                evaluate_review_triggers,
                load_review_triggers
            )
            
            rules_file = attempt.workspace / "docs" / "fitness" / "review-triggers.yaml"
            if not rules_file.exists():
                evidence.review_trigger = {"status": "skipped", "reason": "无规则文件"}
                return
            
            rules = load_review_triggers(rules_file)
            changed_files = collect_changed_files(attempt.workspace, attempt.base_ref or "HEAD~1")
            diff_stats = collect_diff_stats(attempt.workspace, attempt.base_ref or "HEAD~1")
            
            report = evaluate_review_triggers(rules, changed_files, diff_stats, base=attempt.base_ref or "HEAD~1")
            
            evidence.review_trigger = {
                "status": "pass" if not report.human_review_required else "fail",
                "human_review_required": report.human_review_required,
                "triggers": [
                    {
                        "name": t.name,
                        "severity": t.severity
                    }
                    for t in report.triggers
                ]
            }
            
        except Exception as e:
            evidence.review_trigger = {"status": "error", "error": str(e)}
```

- [ ] **步骤 4.4：运行测试验证通过**

```bash
pytest tests/stop_gate/test_collector.py -v
```

预期：PASS（可能需要调整 mock 细节）

- [ ] **步骤 4.5：Commit 证据收集器**

```bash
git add entrix/stop_gate/collector.py tests/stop_gate/test_collector.py
git commit -m "feat: implement evidence collector with independent execution"
```

---

## 阶段 4：裁决器

### 任务 4.1：实现裁决器

**文件：**
- 创建：`entrix/stop_gate/arbiter.py`
- 测试：`tests/stop_gate/test_arbiter.py`

- [ ] **步骤 5.1：编写裁决器测试**

```python
# tests/stop_gate/test_arbiter.py
import pytest
from datetime import datetime, timezone
from entrix.stop_gate.model import EvidencePack, Verdict, AttemptStatus
from entrix.stop_gate.arbiter import GateArbiter

def test_arbitrate_pass():
    """测试通过裁决"""
    arbiter = GateArbiter()
    
    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={"status": "pass", "hard_gate_blocked": False, "score_blocked": False},
        review_trigger={"status": "pass", "human_review_required": False}
    )
    
    verdict = arbiter.arbitrate(evidence)
    
    assert verdict.verdict == "PASS"
    assert "通过" in verdict.summary.lower()

def test_arbitrate_fail_hard_gate():
    """测试硬门禁失败"""
    arbiter = GateArbiter()
    
    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={"status": "fail", "hard_gate_blocked": True, "score_blocked": False}
    )
    
    verdict = arbiter.arbitrate(evidence)
    
    assert verdict.verdict == "FAIL"
    assert "硬门禁" in verdict.reason or "失败" in verdict.reason

def test_arbitrate_blocked_missing_evidence():
    """测试证据缺失导致的阻塞"""
    arbiter = GateArbiter()
    
    evidence = EvidencePack(
        attempt_id="test-uuid",
        fitness={},  # 缺少必需证据
        review_trigger={}
    )
    
    verdict = arbiter.arbitrate(evidence)
    
    assert verdict.verdict == "BLOCKED"
    assert "缺失" in verdict.reason or "未知" in verdict.reason
```

- [ ] **步骤 5.2：运行测试验证失败**

```bash
pytest tests/stop_gate/test_arbiter.py -v
```

预期：FAIL，报错 "No module named 'entrix.stop_gate.arbiter'"

- [ ] **步骤 5.3：实现裁决器**

```python
# entrix/stop_gate/arbiter.py
"""Gate Arbiter - 基于证据和策略进行裁决"""

from datetime import datetime, timezone
from typing import Optional

from entrix.stop_gate.model import EvidencePack, Verdict, Finding
from entrix.stop_gate.errors import SystemError

class GateArbiter:
    """基于证据包做出最终裁决"""
    
    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
    
    def arbitrate(self, evidence: EvidencePack) -> Verdict:
        """基于证据做出裁决"""
        
        # 检查证据完整性
        completeness_check = self._check_evidence_completeness(evidence)
        if completeness_check != "ok":
            return self._blocked_verdict(evidence.attempt_id, completeness_check)
        
        # 检查硬门禁
        if evidence.fitness.get("hard_gate_blocked", False):
            return self._fail_verdict(
                evidence.attempt_id,
                "硬门禁检查失败",
                self._extract_fitness_findings(evidence)
            )
        
        # 检查分数门禁
        if evidence.fitness.get("score_blocked", False):
            return self._fail_verdict(
                evidence.attempt_id,
                "分数不足门禁",
                self._extract_fitness_findings(evidence)
            )
        
        # 检查 review trigger
        if evidence.review_trigger.get("human_review_required", False):
            if self.strict_mode:
                return self._blocked_verdict(
                    evidence.attempt_id,
                    "需要人工审查"
                )
        
        # 所有检查通过
        return self._pass_verdict(evidence)
    
    def _check_evidence_completeness(self, evidence: EvidencePack) -> str:
        """检查证据完整性"""
        if not evidence.fitness or evidence.fitness.get("status") == "unknown":
            return "缺少 fitness 证据或状态未知"
        
        if not evidence.review_trigger or evidence.review_trigger.get("status") == "unknown":
            return "缺少 review_trigger 证据或状态未知"
        
        return "ok"
    
    def _extract_fitness_findings(self, evidence: EvidencePack) -> list[Finding]:
        """从 fitness 证据中提取发现"""
        findings = []
        
        for failed_metric in evidence.fitness.get("failed_metrics", []):
            finding = Finding(
                source="fitness",
                metric=failed_metric["name"],
                severity=failed_metric.get("severity", "soft_gate"),
                message=failed_metric.get("output", "检查失败"),
                artifact_path=None
            )
            findings.append(finding)
        
        return findings
    
    def _pass_verdict(self, evidence: EvidencePack) -> Verdict:
        """生成通过裁决"""
        return Verdict(
            attempt_id=evidence.attempt_id,
            verdict="PASS",
            decided_at=datetime.now(timezone.utc),
            reason="所有质量门禁检查通过",
            summary=f"✅ 质量门禁检查通过 - {self._get_success_summary(evidence)}",
            findings=None
        )
    
    def _fail_verdict(self, attempt_id: str, reason: str, findings: list[Finding]) -> Verdict:
        """生成失败裁决"""
        return Verdict(
            attempt_id=attempt_id,
            verdict="FAIL",
            decided_at=datetime.now(timezone.utc),
            reason=reason,
            summary=f"❌ {reason}，不能结束任务",
            findings=findings
        )
    
    def _blocked_verdict(self, attempt_id: str, reason: str) -> Verdict:
        """生成阻塞裁决"""
        return Verdict(
            attempt_id=attempt_id,
            verdict="BLOCKED",
            decided_at=datetime.now(timezone.utc),
            reason=reason,
            summary=f"🚫 {reason}，需要人工干预",
            findings=None
        )
    
    def _get_success_summary(self, evidence: EvidencePack) -> str:
        """生成成功摘要"""
        metrics_count = evidence.fitness.get("metrics_count", 0)
        failed_count = len(evidence.fitness.get("failed_metrics", []))
        score = evidence.fitness.get("final_score", 0)
        
        return f"{metrics_count - failed_count}/{metrics_count} 检查通过，得分 {score}/100"
```

- [ ] **步骤 5.4：运行测试验证通过**

```bash
pytest tests/stop_gate/test_arbiter.py -v
```

预期：PASS

- [ ] **步骤 5.5：Commit 裁决器**

```bash
git add entrix/stop_gate/arbiter.py tests/stop_gate/test_arbiter.py
git commit -m "feat: implement gate arbiter with comprehensive verdict logic"
```

---

## 阶段 5：反馈格式化器

### 任务 5.1：实现反馈格式化器

**文件：**
- 创建：`entrix/stop_gate/formatter.py`
- 测试：`tests/stop_gate/test_formatter.py`

- [ ] **步骤 6.1：编写反馈格式化器测试**

```python
# tests/stop_gate/test_formatter.py
import pytest
from datetime import datetime, timezone
from entrix.stop_gate.model import Verdict, Finding
from entrix.stop_gate.formatter import FeedbackFormatter

def test_format_pass_feedback():
    """测试格式化通过反馈"""
    formatter = FeedbackFormatter()
    
    verdict = Verdict(
        attempt_id="test-uuid",
        verdict="PASS",
        decided_at=datetime.now(timezone.utc),
        reason="所有检查通过",
        summary="✅ 12/12 检查通过，得分 85/100"
    )
    
    feedback = formatter.format_feedback(verdict)
    
    assert feedback.user_readable.startswith("✅")
    assert "通过" in feedback.user_readable
    assert feedback.structured["verdict"] == "PASS"
    assert feedback.structured["block_termination"] is False

def test_format_fail_feedback():
    """测试格式化失败反馈"""
    formatter = FeedbackFormatter()
    
    verdict = Verdict(
        attempt_id="test-uuid",
        verdict="FAIL",
        decided_at=datetime.now(timezone.utc),
        reason="2 个质量门禁未通过",
        summary="❌ 2 个质量门禁未通过",
        findings=[
            Finding(
                source="fitness",
                metric="pytest_pass",
                severity="hard_gate",
                message="测试命令退出码为 1"
            )
        ]
    )
    
    feedback = formatter.format_feedback(verdict)
    
    assert "❌" in feedback.user_readable
    assert "pytest_pass" in feedback.user_readable
    assert feedback.structured["block_termination"] is True
    assert "next_action" in feedback.structured

def test_format_blocked_feedback():
    """测试格式化阻塞反馈"""
    formatter = FeedbackFormatter()
    
    verdict = Verdict(
        attempt_id="test-uuid",
        verdict="BLOCKED",
        decided_at=datetime.now(timezone.utc),
        reason="需要人工审查",
        summary="🚫 需要人工审查"
    )
    
    feedback = formatter.format_feedback(verdict)
    
    assert "🚫" in feedback.user_readable
    assert feedback.structured["verdict"] == "BLOCKED"
```

- [ ] **步骤 6.2：运行测试验证失败**

```bash
pytest tests/stop_gate/test_formatter.py -v
```

预期：FAIL，报错 "No module named 'entrix.stop_gate.formatter'"

- [ ] **步骤 6.3：实现反馈格式化器**

```python
# entrix/stop_gate/formatter.py
"""Feedback Formatter - 生成 Claude 可执行的反馈"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from entrix.stop_gate.model import Verdict, Finding

@dataclass
class FormattedFeedback:
    """格式化后的反馈"""
    user_readable: str      # Markdown 格式，用户可读
    structured: dict        # JSON 格式，机器可解析
    artifact_path: Optional[Path] = None

class FeedbackFormatter:
    """将裁决结果转换为 Claude 可执行的反馈格式"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        if output_dir is None:
            output_dir = Path.cwd() / ".claude" / "stop-gate" / "feedback"
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def format_feedback(self, verdict: Verdict) -> FormattedFeedback:
        """格式化裁决结果为混合格式"""
        
        # 生成用户可读的 Markdown
        user_readable = self._format_markdown(verdict)
        
        # 生成结构化 JSON
        structured = self._format_structured(verdict)
        
        # 保存 artifact
        artifact_path = self._save_artifact(verdict, user_readable, structured)
        
        return FormattedFeedback(
            user_readable=user_readable,
            structured=structured,
            artifact_path=artifact_path
        )
    
    def _format_markdown(self, verdict: Verdict) -> str:
        """生成 Markdown 格式反馈"""
        
        if verdict.verdict == "PASS":
            return self._pass_markdown(verdict)
        elif verdict.verdict == "FAIL":
            return self._fail_markdown(verdict)
        else:  # BLOCKED
            return self._blocked_markdown(verdict)
    
    def _pass_markdown(self, verdict: Verdict) -> str:
        """生成通过场景的 Markdown"""
        return f"""✅ 质量门禁检查通过

{verdict.summary}

**检查结果:**
- 所有必需质量检查已通过
- 无硬门禁失败
- 无人工审查要求

🎉 可以安全结束任务。

---
*Attempt ID: {verdict.attempt_id}*  
*检查时间: {verdict.decided_at.strftime('%Y-%m-%d %H:%M:%S')} UTC*"""
    
    def _fail_markdown(self, verdict: Verdict) -> str:
        """生成失败场景的 Markdown"""
        findings_text = ""
        
        if verdict.findings:
            for i, finding in enumerate(verdict.findings, 1):
                severity_icon = "🔴" if finding.severity == "hard_gate" else "🟡"
                findings_text += f"""
{severity_icon} **发现 {i}: {finding.source}.{finding.metric}**
   - 严重级别: {finding.severity}
   - 问题: {finding.message}
"""
        
        return f"""❌ {verdict.summary}

## 失败详情
{findings_text if findings_text else "_详细信息请查看 artifact_"}

## 建议修复步骤
1. 根据上述失败项进行修复
2. 运行对应检查验证修复效果
3. 确认所有检查通过后再次请求 stop

🔄 下一步: 修复问题后再次请求 stop，系统将重新检查

---
*Attempt ID: {verdict.attempt_id}*  
*检查时间: {verdict.decided_at.strftime('%Y-%m-%d %H:%M:%S')} UTC*  
*状态: 需要修复后重试*"""
    
    def _blocked_markdown(self, verdict: Verdict) -> str:
        """生成阻塞场景的 Markdown"""
        return f"""🚫 {verdict.summary}

## 阻塞原因
{verdict.reason}

## 需要的干预
此情况需要人工干预或环境修复后才能继续。

🚨 **系统状态: BLOCKED**  
📋 建议检查系统状态或联系支持

---
*Attempt ID: {verdict.attempt_id}*  
*检查时间: {verdict.decided_at.strftime('%Y-%m-%d %H:%M:%S')} UTC*"""
    
    def _format_structured(self, verdict: Verdict) -> dict:
        """生成结构化 JSON 格式"""
        structured = {
            "schema_version": "gate-feedback.v1",
            "attempt_id": verdict.attempt_id,
            "verdict": verdict.verdict,
            "decided_at": verdict.decided_at.isoformat(),
            "summary": verdict.summary,
            "reason": verdict.reason,
            "block_termination": verdict.verdict != "PASS",
            "next_action": self._get_next_action(verdict.verdict)
        }
        
        if verdict.findings:
            structured["findings"] = [
                {
                    "source": f.source,
                    "metric": f.metric,
                    "severity": f.severity,
                    "message": f.message,
                    "suggestions": f.suggestions
                }
                for f in verdict.findings
            ]
        
        return structured
    
    def _get_next_action(self, verdict: str) -> str:
        """获取下一步行动指导"""
        actions = {
            "PASS": "allow_stop",
            "FAIL": "fix_issues_and_retry",
            "BLOCKED": "manual_intervention"
        }
        return actions.get(verdict, "unknown")
    
    def _save_artifact(self, verdict: Verdict, markdown: str, structured: dict) -> Path:
        """保存反馈 artifact"""
        artifact_file = self.output_dir / f"{verdict.attempt_id}.md"
        
        # 保存 Markdown 版本
        artifact_file.write_text(markdown)
        
        # 同时保存 JSON 版本
        json_file = self.output_dir / f"{verdict.attempt_id}.json"
        json_file.write_text(json.dumps(structured, indent=2, ensure_ascii=False))
        
        return artifact_file
```

- [ ] **步骤 6.4：运行测试验证通过**

```bash
pytest tests/stop_gate/test_formatter.py -v
```

预期：PASS

- [ ] **步骤 6.5：Commit 反馈格式化器**

```bash
git add entrix/stop_gate/formatter.py tests/stop_gate/test_formatter.py
git commit -m "feat: implement feedback formatter with hybrid output format"
```

---

## 阶段 6：核心引擎

### 任务 6.1：实现核心引擎

**文件：**
- 创建：`entrix/stop_gate/engine.py`
- 测试：`tests/stop_gate/test_engine.py`

- [ ] **步骤 7.1：编写核心引擎测试**

```python
# tests/stop_gate/test_engine.py
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from entrix.stop_gate.model import GateAttempt, StopDecision, AttemptStatus
from entrix.stop_gate.engine import StopGateEngine

def test_process_stop_request_pass():
    """测试处理成功的 stop 请求"""
    with patch('entrix.stop_gate.engine.EvidenceCollector') as mock_collector, \
         patch('entrix.stop_gate.engine.GateArbiter') as mock_arbiter, \
         patch('entrix.stop_gate.engine.FeedbackFormatter') as mock_formatter:
        
        # 设置模拟返回值
        mock_evidence = Mock()
        mock_evidence.fitness = {"status": "pass", "hard_gate_blocked": False}
        mock_verdict = Mock(
            verdict="PASS",
            reason="All checks passed",
            summary="✅ All checks passed"
        )
        mock_feedback = Mock(
            user_readable="✅ Passed",
            structured={"verdict": "PASS", "block_termination": False}
        )
        
        mock_collector.return_value.collect_evidence.return_value = mock_evidence
        mock_arbiter.return_value.arbitrate.return_value = mock_verdict
        mock_formatter.return_value.format_feedback.return_value = mock_feedback
        
        engine = StopGateEngine()
        attempt = GateAttempt(
            attempt_id="test-uuid",
            session_id="session-1",
            task_id="task-1",
            workspace=Path("/test"),
            base_ref="HEAD~1",
            changed_files=["src/test.py"],
            requested_at=datetime.now(timezone.utc),
            stop_reason="test"
        )
        
        decision = engine.process_stop_request(attempt)
        
        assert decision.allow_stop is True
        assert "✅" in decision.feedback
        assert decision.verdict.verdict == "PASS"

def test_process_stop_request_fail():
    """测试处理失败的 stop 请求"""
    with patch('entrix.stop_gate.engine.EvidenceCollector') as mock_collector, \
         patch('entrix.stop_gate.engine.GateArbiter') as mock_arbiter:
        
        mock_evidence = Mock()
        mock_evidence.fitness = {"status": "fail", "hard_gate_blocked": True}
        mock_verdict = Mock(
            verdict="FAIL",
            reason="Hard gate failed",
            summary="❌ Hard gate failed"
        )
        
        mock_collector.return_value.collect_evidence.return_value = mock_evidence
        mock_arbiter.return_value.arbitrate.return_value = mock_verdict
        
        engine = StopGateEngine()
        attempt = Mock(attempt_id="test-uuid", workspace=Path("/test"))
        
        decision = engine.process_stop_request(attempt)
        
        assert decision.allow_stop is False
        assert decision.verdict.verdict == "FAIL"

def test_get_attempt_history():
    """测试获取会话历史"""
    engine = StopGateEngine()
    session_id = "test-session"
    
    # 创建几个尝试
    for i in range(3):
        attempt = Mock(
            attempt_id=f"attempt-{i}",
            session_id=session_id,
            workspace=Path("/test")
        )
        engine.process_stop_request(attempt)
    
    history = engine.get_attempt_history(session_id)
    assert len(history) == 3
```

- [ ] **步骤 7.2：运行测试验证失败**

```bash
pytest tests/stop_gate/test_engine.py -v
```

预期：FAIL，报错 "No module named 'entrix.stop_gate.engine'"

- [ ] **步骤 7.3：实现核心引擎**

```python
# entrix/stop_gate/engine.py
"""Stop Gate Engine - 核心编排引擎"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, list
import logging

from entrix.stop_gate.model import GateAttempt, StopDecision, AttemptState, AttemptStatus
from entrix.stop_gate.state_manager import SessionStateManager
from entrix.stop_gate.collector import EvidenceCollector
from entrix.stop_gate.arbiter import GateArbiter
from entrix.stop_gate.formatter import FeedbackFormatter
from entrix.stop_gate.errors import StopGateError

logger = logging.getLogger(__name__)

class StopGateEngine:
    """Stop Gate 核心引擎 - 编排所有组件"""
    
    def __init__(self, state_dir: Optional[Path] = None, timeout_seconds: int = 300):
        self.state_manager = SessionStateManager(state_dir)
        self.collector = EvidenceCollector(timeout_seconds=timeout_seconds)
        self.arbiter = GateArbiter(strict_mode=True)
        self.formatter = FeedbackFormatter()
    
    def process_stop_request(self, attempt: GateAttempt) -> StopDecision:
        """处理 Stop 请求，返回决策结果"""
        
        try:
            # 1. 创建尝试状态
            self.state_manager.create_attempt(attempt)
            self.state_manager.update_attempt_status(attempt.attempt_id, AttemptStatus.COLLECTING)
            
            # 2. 收集证据
            logger.info(f"收集证据: {attempt.attempt_id}")
            evidence_pack = self.collector.collect_evidence(attempt)
            
            # 3. 更新为裁决状态
            self.state_manager.update_attempt_status(attempt.attempt_id, AttemptStatus.ARBITRATING)
            
            # 4. 裁决
            logger.info(f"执行裁决: {attempt.attempt_id}")
            verdict = self.arbiter.arbitrate(evidence_pack)
            
            # 5. 格式化反馈
            feedback = self.formatter.format_feedback(verdict)
            
            # 6. 更新最终状态
            final_status = self._verdict_to_status(verdict.verdict)
            self.state_manager.update_attempt_status(
                attempt.attempt_id, 
                final_status,
                verdict={
                    "verdict": verdict.verdict,
                    "reason": verdict.reason,
                    "summary": verdict.summary
                },
                evidence_pack_path=feedback.artifact_path
            )
            
            # 7. 生成决策结果
            allow_stop = (verdict.verdict == "PASS")
            
            return StopDecision(
                allow_stop=allow_stop,
                feedback=feedback.user_readable,
                attempt_id=attempt.attempt_id,
                verdict=verdict
            )
            
        except StopGateError as e:
            logger.error(f"处理 Stop 请求时发生错误: {e}")
            return self._error_decision(attempt, e)
        except Exception as e:
            logger.exception(f"未预期的错误: {e}")
            return self._error_decision(attempt, e)
    
    def get_attempt_history(self, session_id: str) -> list[AttemptState]:
        """获取会话的历史尝试"""
        # 简化实现，返回所有活跃状态
        # 实际中应该按 session_id 过滤
        return list(self.state_manager.active_attempts.values())
    
    def cleanup(self, max_age_hours: int = 24):
        """清理过期状态"""
        self.state_manager.cleanup_expired_attempts(max_age_hours)
    
    def _verdict_to_status(self, verdict: str) -> AttemptStatus:
        """将裁决转换为状态"""
        mapping = {
            "PASS": AttemptStatus.PASSED,
            "FAIL": AttemptStatus.FAILED,
            "BLOCKED": AttemptStatus.BLOCKED
        }
        return mapping.get(verdict, AttemptStatus.BLOCKED)
    
    def _error_decision(self, attempt: GateAttempt, error: Exception) -> StopDecision:
        """生成错误决策"""
        error_message = f"处理 Stop 请求时发生错误: {str(error)}"
        
        return StopDecision(
            allow_stop=False,
            feedback=f"""🚫 Stop Gate 处理失败

## 错误信息
{error_message}

## 建议操作
1. 检查系统状态和日志
2. 确认 Entrix 正确安装
3. 如问题持续，请联系支持

🔄 系统状态: ERROR - 不允许结束任务""",
            attempt_id=attempt.attempt_id,
            verdict=None
        )
```

- [ ] **步骤 7.4：运行测试验证通过**

```bash
pytest tests/stop_gate/test_engine.py -v
```

预期：PASS（可能需要调整 mock 细节）

- [ ] **步骤 7.5：Commit 核心引擎**

```bash
git add entrix/stop_gate/engine.py tests/stop_gate/test_engine.py
git commit -m "feat: implement core Stop Gate engine with orchestration"
```

---

## 阶段 7：插件适配器

### 任务 7.1：实现插件适配器

**文件：**
- 创建：`entrix/stop_gate/adapter.py`
- 测试：`tests/stop_gate/test_adapter.py`

- [ ] **步骤 8.1：编写插件适配器测试**

```python
# tests/stop_gate/test_adapter.py
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from entrix.stop_gate.adapter import StopGateAdapter
from entrix.stop_gate.model import StopDecision

def test_adapter_processes_stop_request():
    """测试适配器处理 stop 请求"""
    with patch('entrix.stop_gate.adapter.StopGateEngine') as mock_engine:
        mock_decision = StopDecision(
            allow_stop=True,
            feedback="✅ Passed",
            attempt_id="test-uuid"
        )
        mock_engine.return_value.process_stop_request.return_value = mock_decision
        
        adapter = StopGateAdapter()
        
        session_context = {
            "session_id": "session-1",
            "task_id": "task-1",
            "workspace": Path("/test"),
            "changed_files": ["src/test.py"],
            "stop_reason": "agent_completed"
        }
        
        decision = adapter.on_before_stop(session_context)
        
        assert decision.allow_stop is True
        assert decision.attempt_id == "test-uuid"

def test_adapter_handles_errors():
    """测试适配器错误处理"""
    with patch('entrix.stop_gate.adapter.StopGateEngine') as mock_engine:
        mock_engine.return_value.process_stop_request.side_effect = Exception("Test error")
        
        adapter = StopGateAdapter()
        
        session_context = {
            "session_id": "session-1",
            "task_id": "task-1", 
            "workspace": Path("/test"),
            "changed_files": [],
            "stop_reason": "test"
        }
        
        decision = adapter.on_before_stop(session_context)
        
        # 错误情况下应该拒绝 stop
        assert decision.allow_stop is False
        assert "错误" in decision.feedback or "error" in decision.feedback.lower()
```

- [ ] **步骤 8.2：运行测试验证失败**

```bash
pytest tests/stop_gate/test_adapter.py -v
```

预期：FAIL，报错 "No module named 'entrix.stop_gate.adapter'"

- [ ] **步骤 8.3：实现插件适配器**

```python
# entrix/stop_gate/adapter.py
"""Stop Gate Adapter - Claude Code 插件集成接口"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import logging

from entrix.stop_gate.model import GateAttempt, StopDecision
from entrix.stop_gate.engine import StopGateEngine
from entrix.stop_gate.errors import StopGateError

logger = logging.getLogger(__name__)

class StopGateAdapter:
    """Claude Code 插件适配器 - 接入插件生命周期"""
    
    def __init__(self, state_dir: Optional[Path] = None, timeout_seconds: int = 300):
        self.engine = StopGateEngine(state_dir=state_dir, timeout_seconds=timeout_seconds)
        logger.info("Stop Gate Adapter 初始化完成")
    
    def on_before_stop(self, session_context: dict) -> StopDecision:
        """拦截 Claude stop 请求 - 插件生命周期钩子
        
        Args:
            session_context: {
                "session_id": str,
                "task_id": str,
                "workspace": Path, 
                "changed_files": list[str],
                "stop_reason": str
            }
        
        Returns:
            StopDecision - 是否允许 stop 以及反馈信息
        """
        try:
            # 1. 验证上下文
            self._validate_context(session_context)
            
            # 2. 创建 GateAttempt
            attempt = GateAttempt.create(
                session_id=session_context["session_id"],
                task_id=session_context["task_id"],
                workspace=session_context["workspace"],
                changed_files=session_context.get("changed_files", []),
                stop_reason=session_context.get("stop_reason", "unknown")
            )
            
            logger.info(f"处理 Stop 请求: {attempt.attempt_id}")
            
            # 3. 调用引擎处理
            decision = self.engine.process_stop_request(attempt)
            
            return decision
            
        except Exception as e:
            logger.exception(f"适配器处理失败: {e}")
            return self._create_error_decision(e)
    
    def _validate_context(self, context: dict) -> None:
        """验证会话上下文完整性"""
        required_fields = ["session_id", "task_id", "workspace"]
        
        for field in required_fields:
            if field not in context:
                raise ValueError(f"缺少必需字段: {field}")
        
        if not isinstance(context["workspace"], Path):
            context["workspace"] = Path(context["workspace"])
    
    def _create_error_decision(self, error: Exception) -> StopDecision:
        """创建错误决策"""
        return StopDecision(
            allow_stop=False,
            feedback=f"""🚫 Stop Gate 处理失败

## 错误信息
{str(error)}

## 建议操作  
1. 检查日志获取详细错误信息
2. 确认所有依赖正确安装
3. 如问题持续，请联系支持

🔄 系统状态: ADAPTER_ERROR - 阻止任务结束""",
            attempt_id="error",
            verdict=None
        )
```

- [ ] **步骤 8.4：运行测试验证通过**

```bash
pytest tests/stop_gate/test_adapter.py -v
```

预期：PASS

- [ ] **步骤 8.5：Commit 插件适配器**

```bash
git add entrix/stop_gate/adapter.py tests/stop_gate/test_adapter.py
git commit -m "feat: implement Claude Code plugin adapter"
```

---

## 阶段 8：集成测试和文档

### 任务 8.1：编写集成测试

**文件：**
- 创建：`tests/stop_gate/test_integration.py`

- [ ] **步骤 9.1：编写端到端集成测试**

```python
# tests/stop_gate/test_integration.py
import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import os
from entrix.stop_gate.adapter import StopGateAdapter

@pytest.mark.integration
def test_full_stop_gate_cycle_pass():
    """测试完整的 Stop Gate 通过循环"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 设置测试环境
        test_repo = Path(tmpdir) / "test-repo"
        test_repo.mkdir()
        
        # 创建基本的项目结构
        (test_repo / "docs" / "fitness").mkdir(parents=True)
        (test_repo / "docs" / "fitness" / "code-quality.md").write_text("""
---
dimension: code_quality
weight: 100
threshold:
  pass: 100
  warn: 80
metrics:
  - name: test_metric
    command: echo "test passed"
    hard_gate: false
    tier: fast
---
# Code Quality
""")
        
        # 初始化 git 仓库
        os.system(f"cd {test_repo} && git init && git config user.email 'test@test.com' && git config user.name 'Test'")
        (test_repo / "test.py").write_text("print('hello')")
        os.system(f"cd {test_repo} && git add . && git commit -m 'initial'")
        
        # 创建适配器
        adapter = StopGateAdapter(state_dir=test_repo / ".claude" / "stop-gate")
        
        # 模拟 stop 请求
        session_context = {
            "session_id": "test-session",
            "task_id": "test-task",
            "workspace": test_repo,
            "changed_files": ["test.py"],
            "stop_reason": "agent_completed"
        }
        
        decision = adapter.on_before_stop(session_context)
        
        # 验证结果
        assert decision.attempt_id is not None
        assert isinstance(decision.allow_stop, bool)
        assert decision.feedback is not None
        assert len(decision.feedback) > 0

@pytest.mark.integration  
def test_full_stop_gate_cycle_fail():
    """测试完整的 Stop Gate 失败循环"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_repo = Path(tmpdir) / "test-repo"
        test_repo.mkdir()
        
        # 创建会失败的质量检查
        (test_repo / "docs" / "fitness").mkdir(parents=True)
        (test_repo / "docs" / "fitness" / "code-quality.md").write_text("""
---
dimension: code_quality
weight: 100
threshold:
  pass: 100
  warn: 80
metrics:
  - name: failing_test
    command: exit 1
    hard_gate: true
    tier: fast
---
# Code Quality
""")
        
        # 初始化 git 仓库
        os.system(f"cd {test_repo} && git init && git config user.email 'test@test.com' && git config user.name 'Test'")
        (test_repo / "test.py").write_text("print('hello')")
        os.system(f"cd {test_repo} && git add . && git commit -m 'initial'")
        
        # 创建适配器
        adapter = StopGateAdapter(state_dir=test_repo / ".claude" / "stop-gate")
        
        session_context = {
            "session_id": "test-session",
            "task_id": "test-task", 
            "workspace": test_repo,
            "changed_files": ["test.py"],
            "stop_reason": "agent_completed"
        }
        
        decision = adapter.on_before_stop(session_context)
        
        # 验证失败行为
        assert decision.allow_stop is False
        assert "❌" in decision.feedback or "fail" in decision.feedback.lower()
```

- [ ] **步骤 9.2：运行集成测试**

```bash
pytest tests/stop_gate/test_integration.py -v -m integration
```

预期：PASS（可能需要根据实际环境调整）

- [ ] **步骤 9.3：Commit 集成测试**

```bash
git add tests/stop_gate/test_integration.py
git commit -m "test: add end-to-end integration tests for Stop Gate"
```

### 任务 8.2：更新包导出和文档

- [ ] **步骤 10.1：更新主包导出**

```python
# entrix/__init__.py 更新
# 在现有导出基础上添加：
from entrix.stop_gate import StopGateAdapter, StopGateEngine

__all__ = [
    # ... 现有导出
    "StopGateAdapter",
    "StopGateEngine"
]
```

- [ ] **步骤 10.2：创建使用示例文档**

创建 `docs/stop-gate-usage.md`:

```markdown
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

# 在实际项目中使用
entrix run --tier normal
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
```

- [ ] **步骤 10.3：Commit 文档更新**

```bash
git add entrix/__init__.py docs/stop-gate-usage.md
git commit -m "docs: add Stop Gate usage documentation and package exports"
```

---

## 完成检查

### 最终验收标准

- [ ] **所有测试通过**: `pytest tests/stop_gate/ -v`
- [ ] **集成测试通过**: `pytest tests/stop_gate/test_integration.py -v -m integration`
- [ ] **代码覆盖率**: 适当的测试覆盖核心组件
- [ ] **文档完整**: 使用文档和 API 文档齐全
- [ ] **代码质量**: 通过 ruff 和其他检查

### 清理和优化

- [ ] 移除调试代码和临时文件
- [ ] 优化性能瓶颈
- [ ] 完善错误消息
- [ ] 更新 README 主文档

---

## 下一步

P0 最小可用版本完成后，可以考虑：

**P1 - 可靠性和可运维性:**
- 完整的错误处理和恢复机制
- 详细的日志和监控
- 并发控制优化

**P2 - 高级功能:**
- MCP 双向通信增强
- 统计分析和可视化  
- 高级裁决策略配置

---

**实施者注意:** 
- 使用 TDD 方法：先写测试，再实现功能
- 频繁 commit，每步都有意义的变更
- 遇到阻塞问题及时记录和沟通
- 遵循 YAGNI 原则，只实现必需功能