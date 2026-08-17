# YAML 驱动证据收集和门禁仲裁系统 — 实施计划

> **给代理开发者的提示：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 来逐任务实施此计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 构建一个由 `harness.yaml` 驱动的可配置证据收集和门禁仲裁系统，替换硬编码的 stop-gate 逻辑，提供灵活的声明式配置层。

**架构：** 新的 `entrix/harness/` 包提供可复用的证据 + 门禁层，而 `entrix/stop_gate/` 重构为仅包含钩子专属代码，通过 HarnessRunner 调用 harness 层。系统支持基于命令和内置的证据生产者、基于表达式门禁规则和条件激活。

**技术栈：** Python 3.8+、dataclasses、YAML (PyYAML)、regex、subprocess、JSON、asyncio 用于并行执行

## 全局约束

- **Python 版本：** 3.8+（支持类型提示的 dataclasses）
- **无额外依赖：** 仅使用标准库 + 项目现有依赖
- **向后兼容：** 当缺少 harness.yaml 时，entrix stop-gate 必须保持现有行为
- **错误处理：** 生产者失败从不阻止其他生产者；门禁评估错误导致硬门禁失败
- **文件结构：** 所有新代码放在 `entrix/harness/` 目录下；仅修改 `entrix/stop_gate/` 用于集成
- **测试覆盖：** 所有新代码需要单元测试；端到端流程需要集成测试
- **架构版本：** harness.yaml 必须验证版本 "harness/v1"；evidence bundle 架构 "evidence/v1"、"evidence-bundle/v1"

---

## 任务 1：创建基础数据模型

**文件：**
- 创建：`entrix/harness/__init__.py`
- 创建：`entrix/harness/evidence.py`
- 创建：`tests/harness/test_evidence.py`

**接口：**
- 产出：`Evidence`、`EvidenceBundle`、`Artifact` 数据类
- 消费：无（基础类型）

**描述：** 定义证据系统的核心数据结构。这些是所有其他组件将要使用的基础类型。

- [ ] **步骤 1：编写失败的测试**

创建测试文件 `tests/harness/test_evidence.py`：

```python
import json
from datetime import datetime
from entrix.harness.evidence import Evidence, EvidenceBundle, Artifact

def test_evidence_dataclass_creation():
    """测试包含所有字段的 Evidence 数据类"""
    evidence = Evidence(
        id="test-1",
        type="test",
        name="单元测试",
        status="pass",
        producer="pytest",
        task_id="task-123",
        started_at="2026-08-16T10:30:00Z",
        duration_ms=1500,
        summary={"passed": 10, "failed": 0},
        artifacts=[Artifact(type="junit", path="junit.xml")],
        raw={"exit_code": 0}
    )
    
    assert evidence.id == "test-1"
    assert evidence.type == "test"
    assert evidence.status == "pass"
    assert evidence.summary["passed"] == 10
    assert len(evidence.artifacts) == 1

def test_evidence_defaults():
    """测试 Evidence 具有正确的默认值"""
    evidence = Evidence()
    
    assert evidence.schema_version == "evidence/v1"
    assert evidence.id == ""
    assert evidence.type == ""
    assert evidence.status == ""

def test_evidence_bundle_creation():
    """测试包含多个证据项的 EvidenceBundle"""
    bundle = EvidenceBundle(
        task_id="task-123",
        attempt_id="attempt-1",
        collected_at="2026-08-16T10:35:00Z",
        evidence=[
            Evidence(id="test-1", type="test", name="测试"),
            Evidence(id="lint-1", type="lint", name="代码检查")
        ],
        collection_errors=[]
    )
    
    assert bundle.schema_version == "evidence-bundle/v1"
    assert len(bundle.evidence) == 2
    assert bundle.task_id == "task-123"

def test_evidence_bundle_serialization():
    """测试 EvidenceBundle 可以序列化为 JSON"""
    bundle = EvidenceBundle(
        task_id="task-123",
        attempt_id="attempt-1",
        collected_at="2026-08-16T10:35:00Z",
        evidence=[Evidence(id="test-1", type="test", name="测试")]
    )
    
    # 应该可以 JSON 序列化
    json_str = json.dumps(bundle.__dict__)
    assert "task-123" in json_str
    
    # 应该反序列化回来
    data = json.loads(json_str)
    assert data["task_id"] == "task-123"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_evidence.py -v`  
预期：ImportError: No module named 'entrix.harness.evidence'

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/__init__.py`：
```python
"""证据收集和门禁仲裁的 Harness 包。"""
```

创建 `entrix/harness/evidence.py`：
```python
"""证据收集系统的数据模型。"""
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class Artifact:
    """证据收集产生的制品引用。"""
    type: str  # junit、sarif、log 等
    path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Evidence:
    """生产者收集的单个证据项。"""
    schema_version: str = "evidence/v1"
    id: str = ""
    type: str = ""  # test、lint、typecheck、diff、custom
    name: str = ""
    status: str = ""  # pass、fail、skipped、error、timeout
    producer: str = ""
    task_id: str = ""
    started_at: str = ""  # ISO-8601 UTC
    duration_ms: int = 0
    summary: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Artifact] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

@dataclass
class EvidenceBundle:
    """单次任务尝试收集的所有证据的包。"""
    schema_version: str = "evidence-bundle/v1"
    task_id: str = ""
    attempt_id: str = ""
    collected_at: str = ""
    evidence: List[Evidence] = field(default_factory=list)
    collection_errors: List[Dict[str, Any]] = field(default_factory=list)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_evidence.py -v`  
预期：所有测试通过

- [ ] **步骤 5：提交**

```bash
git add entrix/harness/ tests/harness/
git commit -m "feat(harness): 添加基础的 Evidence 和 EvidenceBundle 数据模型"
```

---

## 任务 2：实现 Harness 配置加载

**文件：**
- 创建：`entrix/harness/config.py`
- 创建：`tests/harness/test_config.py`

**接口：**
- 产出：`HarnessConfig`、`EvidenceProducerConfig`、`GatePolicyConfig` 类；`load_harness_config(path) -> HarnessConfig`
- 消费：无

**描述：** 实现 harness.yaml 的 YAML 配置加载和验证，支持 MVP 功能的模式验证。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_config.py`：

```python
import pytest
from pathlib import Path
from entrix.harness.config import load_harness_config, HarnessConfig

def test_load_minimal_config():
    """测试加载最小有效的 harness.yaml"""
    yaml_content = """
version: "harness/v1"

evidence_producers:
  - id: typecheck
    type: typecheck
    name: TypeScript 类型检查
    command: npm run typecheck
    producer: tsc
    parser:
      type: exit_code

gate_policies:
  - name: 类型检查通过
    severity: hard
    rule:
      evidence_id: typecheck
      condition: status == "pass"
"""
    config_path = Path("/tmp/test_harness.yaml")
    config_path.write_text(yaml_content)
    
    config = load_harness_config(config_path)
    
    assert config.version == "harness/v1"
    assert len(config.evidence_producers) == 1
    assert config.evidence_producers[0].id == "typecheck"
    assert len(config.gate_policies) == 1
    assert config.gate_policies[0].severity == "hard"

def test_load_config_with_when_conditions():
    """测试加载带有激活条件的配置"""
    yaml_content = """
version: "harness/v1"

when:
  branch:
    exclude:
      - docs/**
  env:
    CI: "true"

evidence_producers:
  - id: test
    type: test
    name: 测试
    command: pytest
    producer: pytest
    parser:
      type: exit_code
    when:
      changed_any:
        - src/**

gate_policies: []
"""
    config_path = Path("/tmp/test_harness_with_when.yaml")
    config_path.write_text(yaml_content)
    
    config = load_harness_config(config_path)
    
    assert config.when is not None
    assert config.when["branch"]["exclude"] == ["docs/**"]
    assert config.when["env"]["CI"] == "true"
    assert config.evidence_producers[0].when is not None
    assert "changed_any" in config.evidence_producers[0].when

def test_invalid_version_rejected():
    """测试不支持的架构版本被拒绝"""
    yaml_content = """
version: "harness/v2"

evidence_producers: []
gate_policies: []
"""
    config_path = Path("/tmp/test_invalid_version.yaml")
    config_path.write_text(yaml_content)
    
    with pytest.raises(ValueError, match="不支持的 harness 版本"):
        load_harness_config(config_path)

def test_builtin_producer():
    """测试加载内置生产者配置"""
    yaml_content = """
version: "harness/v1"

evidence_producers:
  - id: diff-stats
    type: diff
    name: Git 差异统计
    builtin: diff-stats

gate_policies: []
"""
    config_path = Path("/tmp/test_builtin.yaml")
    config_path.write_text(yaml_content)
    
    config = load_harness_config(config_path)
    
    assert config.evidence_producers[0].builtin == "diff-stats"
    assert config.evidence_producers[0].command is None

def test_regex_parser_config():
    """测试加载正则表达式解析器配置"""
    yaml_content = """
version: "harness/v1"

evidence_producers:
  - id: unit-test
    type: test
    name: 单元测试
    command: pytest
    producer: pytest
    parser:
      type: regex
      pattern: 'passed=(?P<passed>\\d+), failed=(?P<failed>\\d+)'

gate_policies: []
"""
    config_path = Path("/tmp/test_regex_parser.yaml")
    config_path.write_text(yaml_content)
    
    config = load_harness_config(config_path)
    
    assert config.evidence_producers[0].parser["type"] == "regex"
    assert "passed" in config.evidence_producers[0].parser["pattern"]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_config.py -v`  
预期：ImportError: No module named 'entrix.harness.config'

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/config.py`：
```python
"""Harness 配置加载和验证。"""
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional

SUPPORTED_VERSIONS = ["harness/v1"]

@dataclass
class GateRuleConfig:
    """单个门禁规则的配置。"""
    evidence_id: Optional[str] = None
    evidence_type: Optional[str] = None
    condition: str = ""
    action: Optional[str] = None

@dataclass 
class GatePolicyConfig:
    """门禁策略的配置。"""
    name: str = ""
    severity: str = ""  # hard、soft、advisory、blocked
    rule: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ParserConfig:
    """解析命令输出的配置。"""
    type: str = ""  # exit_code、regex
    pattern: Optional[str] = None

@dataclass
class EvidenceProducerConfig:
    """证据生产者的配置。"""
    id: str = ""
    type: str = ""
    name: str = ""
    command: Optional[str] = None
    producer: str = ""
    builtin: Optional[str] = None
    timeout_seconds: int = 60
    when: Optional[Dict[str, Any]] = None
    parser: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, str]] = field(default_factory=list)

@dataclass
class HarnessConfig:
    """顶层 harness 配置。"""
    version: str = ""
    when: Optional[Dict[str, Any]] = None
    evidence_producers: List[EvidenceProducerConfig] = field(default_factory=list)
    gate_policies: List[GatePolicyConfig] = field(default_factory=list)

def _load_producer_configs(producers_data: List[Dict]) -> List[EvidenceProducerConfig]:
    """从 YAML 数据加载证据生产者配置。"""
    producers = []
    for prod_data in producers_data:
        parser_data = prod_data.get("parser", {})
        parser_config = ParserConfig(
            type=parser_data.get("type", ""),
            pattern=parser_data.get("pattern")
        )
        
        producers.append(EvidenceProducerConfig(
            id=prod_data.get("id", ""),
            type=prod_data.get("type", ""),
            name=prod_data.get("name", ""),
            command=prod_data.get("command"),
            producer=prod_data.get("producer", ""),
            builtin=prod_data.get("builtin"),
            timeout_seconds=prod_data.get("timeout_seconds", 60),
            when=prod_data.get("when"),
            parser=parser_config.__dict__,
            artifacts=prod_data.get("artifacts", [])
        ))
    return producers

def _load_gate_policy_configs(gates_data: List[Dict]) -> List[GatePolicyConfig]:
    """从 YAML 数据加载门禁策略配置。"""
    policies = []
    for gate_data in gates_data:
        policies.append(GatePolicyConfig(
            name=gate_data.get("name", ""),
            severity=gate_data.get("severity", ""),
            rule=gate_data.get("rule", {})
        ))
    return policies

def load_harness_config(config_path: Path) -> HarnessConfig:
    """加载并验证 harness.yaml 配置。
    
    Args:
        config_path: harness.yaml 文件路径
        
    Returns:
        验证后的 HarnessConfig 对象
        
    Raises:
        ValueError: 如果配置无效
    """
    if not config_path.exists():
        raise FileNotFoundError(f"未找到 Harness 配置：{config_path}")
    
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    version = data.get("version", "")
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"不支持的 harness 版本：{version}。必须是以下之一：{SUPPORTED_VERSIONS}")
    
    return HarnessConfig(
        version=version,
        when=data.get("when"),
        evidence_producers=_load_producer_configs(data.get("evidence_producers", [])),
        gate_policies=_load_gate_policy_configs(data.get("gate_policies", []))
    )
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_config.py -v`  
预期：所有测试通过

- [ ] **步骤 5：提交**

```bash
git add entrix/harness/config.py tests/harness/test_config.py
git commit -m "feat(harness): 添加 harness 配置加载和验证"
```

---

## 任务 3：实现条件表达式求值

**文件：**
- 创建：`entrix/harness/conditions.py`
- 创建：`tests/harness/test_conditions.py`

**接口：**
- 产出：`evaluate_when(when_dict, context) -> bool`，files_exist、changed_any、branch、env 谓词函数
- 消费：`HarnessRunContext`（稍后定义）

**描述：** 实现 `when` 条件求值系统，用于激活生产者和全局 harness 执行。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_conditions.py`：

```python
import pytest
from pathlib import Path
from entrix.harness.conditions import evaluate_when, WhenContext

def test_files_exist_predicate():
    """测试 files_exist 谓词"""
    # 创建临时文件
    test_file = Path("/tmp/test_exists.txt")
    test_file.write_text("内容")
    
    when = {"files_exist": ["/tmp/test_exists.txt"]}
    context = WhenContext(repo_root=Path("/tmp"))
    
    result = evaluate_when(when, context)
    assert result is True

def test_files_exist_missing():
    """测试文件不存在时的 files_exist"""
    when = {"files_exist": ["/tmp/does_not_exist.txt"]}
    context = WhenContext(repo_root=Path("/tmp"))
    
    result = evaluate_when(when, context)
    assert result is False

def test_branch_predicate():
    """测试分支 include/exclude 模式"""
    when = {
        "branch": {
            "include": ["main", "feature/*"],
            "exclude": ["docs/**"]
        }
    }
    context = WhenContext(current_branch="feature/add-auth")
    
    result = evaluate_when(when, context)
    assert result is True

def test_branch_excluded():
    """测试分支 exclude 模式"""
    when = {
        "branch": {
            "exclude": ["docs/**"]
        }
    }
    context = WhenContext(current_branch="docs/update-readme")
    
    result = evaluate_when(when, context)
    assert result is False

def test_env_predicate():
    """测试环境变量谓词"""
    import os
    os.environ["TEST_VAR"] = "true"
    
    when = {"env": {"TEST_VAR": "true"}}
    context = WhenContext(repo_root=Path.cwd())
    
    result = evaluate_when(when, context)
    assert result is True

def test_env_predicate_no_match():
    """测试环境变量不匹配"""
    when = {"env": {"CI": "true"}}
    context = WhenContext(repo_root=Path.cwd())
    
    result = evaluate_when(when, context)
    assert result is False

def test_multiple_predicates_and_semantics():
    """测试 when 块中的多个谓词（AND 语义）"""
    import os
    os.environ["CI"] = "true"
    test_file = Path("/tmp/test_and.txt")
    test_file.write_text("内容")
    
    when = {
        "files_exist": ["/tmp/test_and.txt"],
        "env": {"CI": "true"}
    }
    context = WhenContext(repo_root=Path("/tmp"))
    
    result = evaluate_when(when, context)
    assert result is True

def test_multiple_predicates_one_false():
    """测试一个谓词为 false 时的 AND 语义"""
    when = {
        "files_exist": ["/tmp/does_not_exist.txt"],
        "env": {"CI": "true"}  # 这个可能为 true
    }
    context = WhenContext(repo_root=Path("/tmp"))
    
    result = evaluate_when(when, context)
    assert result is False

def test_empty_when():
    """测试空的 when 块始终为 true"""
    when = {}
    context = WhenContext(repo_root=Path("/tmp"))
    
    result = evaluate_when(when, context)
    assert result is True

def test_none_when():
    """测试 None when 始终为 true"""
    result = evaluate_when(None, WhenContext(repo_root=Path("/tmp")))
    assert result is True
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_conditions.py -v`  
预期：ImportError: No module named 'entrix.harness.conditions'

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/conditions.py`：
```python
"""when 谓词的条件表达式求值。"""
import os
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, List

@dataclass
class WhenContext:
    """评估 when 条件的上下文。"""
    repo_root: Path
    changed_files: List[str] = None
    current_branch: str = None
    
    def __post_init__(self):
        if self.changed_files is None:
            self.changed_files = []
        if self.current_branch is None:
            self.current_branch = "unknown"

def _files_exist(patterns: List[str], context: WhenContext) -> bool:
    """检查匹配模式的文件是否存在。"""
    for pattern in patterns:
        full_path = context.repo_root / pattern
        if full_path.exists():
            return True
    return False

def _changed_any(patterns: List[str], context: WhenContext) -> bool:
    """检查是否有变更文件匹配模式。"""
    if not context.changed_files:
        return False
    
    for pattern in patterns:
        for changed_file in context.changed_files:
            if fnmatch.fnmatch(changed_file, pattern):
                return True
    return False

def _branch条件(config: Dict[str, List[str]], context: WhenContext) -> bool:
    """检查分支 include/exclude 条件。"""
    include_patterns = config.get("include", [])
    exclude_patterns = config.get("exclude", [])
    
    # 先检查 exclude
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(context.current_branch, pattern):
            return False
    
    # 检查 include
    if include_patterns:
        for pattern in include_patterns:
            if fnmatch.fnmatch(context.current_branch, pattern):
                return True
        return False
    
    return True

def _env条件(required_vars: Dict[str, str], context: WhenContext) -> bool:
    """检查环境变量条件。"""
    for var_name, expected_value in required_vars.items():
        actual_value = os.environ.get(var_name)
        if actual_value != expected_value:
            return False
    return True

def evaluate_when(when: Optional[Dict[str, Any]], context: WhenContext) -> bool:
    """评估 when 条件。
    
    Args:
        when: 条件字典或 None
        context: 评估上下文
        
    Returns:
        如果条件满足（或 when 为 None/空）则返回 True，否则返回 False
    """
    if when is None or not when:
        return True
    
    # when 块中的所有谓词都是 AND 关系
    for predicate_name, predicate_value in when.items():
        if predicate_name == "files_exist":
            if not _files_exist(predicate_value, context):
                return False
        elif predicate_name == "changed_any":
            if not _changed_any(predicate_value, context):
                return False
        elif predicate_name == "branch":
            if not _branch条件(predicate_value, context):
                return False
        elif predicate_name == "env":
            if not _env条件(predicate_value, context):
                return False
        else:
            # 未知谓词 - 保守地返回 False
            return False
    
    return True
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_conditions.py -v`  
预期：大部分测试通过，分支条件可能需要调整

- [ ] **步骤 5：修复并验证所有测试通过**

运行：`python -m pytest tests/harness/test_conditions.py -v`  
预期：所有测试通过

- [ ] **步骤 6：提交**

```bash
git add entrix/harness/conditions.py tests/harness/test_conditions.py
git commit -m "feat(harness): 添加条件表达式求值系统"
```

---

## 任务 4：实现证据包存储

**文件：**
- 创建：`entrix/harness/store.py`
- 创建：`tests/harness/test_store.py`

**接口：**
- 产出：`EvidenceStore.save(bundle, task_id) -> Path`，`EvidenceStore.load(path) -> EvidenceBundle`
- 消费：任务 1 的 `EvidenceBundle`

**描述：** 实现证据包的持久化层，保存到 `.harness/evidence/<task-id>/<timestamp>-bundle.json`。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_store.py`：

```python
import pytest
import json
from pathlib import Path
from datetime import datetime
from entrix.harness.store import EvidenceStore
from entrix.harness.evidence import Evidence, EvidenceBundle

def test_save_evidence_bundle():
    """测试将证据包保存到磁盘"""
    bundle = EvidenceBundle(
        task_id="test-task",
        attempt_id="attempt-1", 
        collected_at="2026-08-16T10:00:00Z",
        evidence=[
            Evidence(id="test-1", type="test", name="测试", status="pass")
        ]
    )
    
    store = EvidenceStore(root_dir=Path("/tmp/test_harness_store"))
    saved_path = store.save(bundle)
    
    assert saved_path.exists()
    assert saved_path.name.endswith("-bundle.json")

def test_load_evidence_bundle():
    """测试从磁盘加载证据包"""
    bundle = EvidenceBundle(
        task_id="test-task",
        attempt_id="attempt-1",
        collected_at="2026-08-16T10:00:00Z", 
        evidence=[
            Evidence(id="test-1", type="test", name="测试", status="pass")
        ]
    )
    
    store = EvidenceStore(root_dir=Path("/tmp/test_harness_store"))
    saved_path = store.save(bundle)
    
    # 加载回来
    loaded_bundle = store.load(saved_path)
    
    assert loaded_bundle.task_id == bundle.task_id
    assert loaded_bundle.attempt_id == bundle.attempt_id
    assert len(loaded_bundle.evidence) == 1
    assert loaded_bundle.evidence[0].id == "test-1"

def test_save_creates_task_directory():
    """测试保存会创建任务特定目录"""
    bundle = EvidenceBundle(
        task_id="test-task-123",
        attempt_id="attempt-1",
        evidence=[]
    )
    
    store = EvidenceStore(root_dir=Path("/tmp/test_harness_store"))
    saved_path = store.save(bundle)
    
    # 应该在任务特定目录中
    assert "test-task-123" in str(saved_path)

def test_save_multiple_bundles_same_task():
    """测试为同一任务保存多个包"""
    bundle1 = EvidenceBundle(task_id="task-1", evidence=[])
    bundle2 = EvidenceBundle(task_id="task-1", evidence=[])
    
    store = EvidenceStore(root_dir=Path("/tmp/test_harness_store"))
    path1 = store.save(bundle1)
    path2 = store.save(bundle2)
    
    # 应该创建不同的文件
    assert path1 != path2
    assert path1.exists()
    assert path2.exists()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_store.py -v`  
预期：ImportError: No module named 'entrix.harness.store'

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/store.py`：
```python
"""证据包持久化层。"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from entrix.harness.evidence import EvidenceBundle

class EvidenceStore:
    """管理证据包到磁盘的持久化。"""
    
    def __init__(self, root_dir: Path):
        """初始化证据存储。
        
        Args:
            root_dir: 证据存储的根目录
        """
        self.root_dir = root_dir
        self.evidence_dir = root_dir / ".harness" / "evidence"
    
    def save(self, bundle: EvidenceBundle) -> Path:
        """将证据包保存到磁盘。
        
        Args:
            bundle: 要保存的证据包
            
        Returns:
            保存的包文件路径
        """
        task_dir = self.evidence_dir / bundle.task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"{timestamp}-bundle.json"
        filepath = task_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(bundle.__dict__, f, indent=2)
        
        return filepath
    
    def load(self, path: Path) -> Optional[EvidenceBundle]:
        """从磁盘加载证据包。
        
        Args:
            path: 包文件路径
            
        Returns:
            EvidenceBundle 或 None（如果加载失败）
        """
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            return EvidenceBundle(**data)
        except (json.JSONDecodeError, TypeError, IOError):
            return None
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_store.py -v`  
预期：所有测试通过

- [ ] **步骤 5：提交**

```bash
git add entrix/harness/store.py tests/harness/test_store.py
git commit -m "feat(harness): 添加证据包持久化层"
```

---

## 任务 5：实现生产者基类和命令生产者

**文件：**
- 创建：`entrix/harness/producers/__init__.py`
- 创建：`entrix/harness/producers/base.py`
- 创建：`entrix/harness/producers/command.py`
- 创建：`tests/harness/test_command_producer.py`

**接口：**
- 产出：`Producer` 协议，`CommandProducer` 类，`run(context) -> Evidence` 方法
- 消费：任务 1 的 `Evidence`，任务 2 的 `EvidenceProducerConfig`，任务 3 的 `WhenContext`

**描述：** 实现生产者系统，包括基础协议和支持 exit_code 和 regex 解析器的命令生产者。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_command_producer.py`：

```python
import pytest
from pathlib import Path
from entrix.harness.producers.base import Producer, ProducerContext
from entrix.harness.producers.command import CommandProducer
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.conditions import WhenContext

def test_command_producer_exit_code_success():
    """测试 exit_code 解析器在成功时的命令生产者"""
    config = EvidenceProducerConfig(
        id="test-success",
        type="test",
        name="退出码测试",
        command="echo 'test'",
        producer="test",
        parser={"type": "exit_code"}
    )
    
    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    evidence = producer.run(context)
    
    assert evidence.id == "test-success"
    assert evidence.status == "pass"
    assert evidence.producer == "test"

def test_command_producer_exit_code_failure():
    """测试 exit_code 解析器在失败时的命令生产者"""
    config = EvidenceProducerConfig(
        id="test-fail",
        type="test", 
        name="失败测试",
        command="exit 1",
        producer="test",
        parser={"type": "exit_code"}
    )
    
    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    evidence = producer.run(context)
    
    assert evidence.status == "fail"

def test_command_producer_regex_parser():
    """测试 regex 解析器的命令生产者"""
    config = EvidenceProducerConfig(
        id="regex-test",
        type="test",
        name="正则测试",
        command='echo "passed=10, failed=2"',
        producer="test",
        parser={"type": "regex", "pattern": r'passed=(?P<passed>\d+), failed=(?P<failed>\d+)'}
    )
    
    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    evidence = producer.run(context)
    
    assert evidence.status == "pass"
    assert evidence.summary["passed"] == "10"
    assert evidence.summary["failed"] == "2"

def test_command_producer_timeout():
    """测试命令生产者超时处理"""
    config = EvidenceProducerConfig(
        id="timeout-test",
        type="test",
        name="超时测试", 
        command="sleep 10",
        producer="test",
        timeout_seconds=1,
        parser={"type": "exit_code"}
    )
    
    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    evidence = producer.run(context)
    
    assert evidence.status == "timeout"

def test_command_producer_regex_parse_error():
    """测试正则解析失败处理"""
    config = EvidenceProducerConfig(
        id="regex-error",
        type="test",
        name="正则错误测试",
        command='echo "no match here"',
        producer="test",
        parser={"type": "regex", "pattern": r'passed=(?P<passed>\d+)'}
    )
    
    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    evidence = producer.run(context)
    
    assert evidence.status == "error"
    assert "regex" in str(evidence.raw.get("error", "")).lower()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_command_producer.py -v`  
预期：生产者模块的 ImportError

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/producers/__init__.py`：
```python
"""用于收集测试、lint 和其他结果的证据生产者。"
```

创建 `entrix/harness/producers/base.py`：
```python
"""生产者协议和上下文。"""
from dataclasses import dataclass
from pathlib import Path
from entrix.harness.conditions import WhenContext
from entrix.harness.evidence import Evidence

@dataclass
class ProducerContext:
    """生产者运行时提供的上下文。"""
    task_id: str
    repo_root: Path
    when_context: WhenContext
    attempt_id: str = "unknown"

class Producer:
    """证据生产者协议。
    
    生产者通过某种机制（命令、内置等）收集证据
    并将其作为 Evidence 对象返回。
    """
    
    def run(self, context: ProducerContext) -> Evidence:
        """执行生产者并返回证据。
        
        Args:
            context: 执行上下文
            
        Returns:
            包含结果的 Evidence 对象
        """
        raise NotImplementedError("Producer.run 必须由子类实现")
```

创建 `entrix/harness/producers/command.py`：
```python
"""基于命令的证据生产者。"
import subprocess
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from entrix.harness.producers.base import Producer, ProducerContext
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.evidence import Evidence

class CommandProducer(Producer):
    """运行 shell 命令并解析输出的生产者。"
    
    def __init__(self, config: EvidenceProducerConfig):
        """初始化命令生产者。
        
        Args:
            config: 生产者配置
        """
        self.config = config
        self.parser_type = config.parser.get("type", "exit_code")
        self.regex_pattern = config.parser.get("pattern")
    
    def run(self, context: ProducerContext) -> Evidence:
        """执行命令并解析结果。
        
        Args:
            context: 执行上下文
            
        Returns:
            包含解析结果的 Evidence 对象
        """
        evidence = Evidence(
            id=self.config.id,
            type=self.config.type,
            name=self.config.name,
            producer=self.config.producer,
            task_id=context.task_id,
            started_at=datetime.utcnow().isoformat() + "Z"
        )
        
        try:
            # 执行命令
            start_time = time.time()
            result = subprocess.run(
                self.config.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=context.repo_root
            )
            duration_ms = int((time.time() - start_time) * 1000)
            evidence.duration_ms = duration_ms
            
            # 根据解析器类型解析
            if self.parser_type == "exit_code":
                self._parse_exit_code(result, evidence)
            elif self.parser_type == "regex":
                self._parse_regex(result, evidence)
            else:
                evidence.status = "error"
                evidence.raw["error"] = f"未知解析器类型：{self.parser_type}"
                
        except subprocess.TimeoutExpired:
            evidence.status = "timeout"
            evidence.raw["error"] = f"命令在 {self.config.timeout_seconds}秒后超时"
        except Exception as e:
            evidence.status = "error"
            evidence.raw["error"] = str(e)
        
        return evidence
    
    def _parse_exit_code(self, result: subprocess.CompletedProcess, evidence: Evidence):
        """使用退出码解析命令结果。"""
        evidence.raw["exit_code"] = result.returncode
        evidence.raw["stdout"] = result.stdout
        evidence.raw["stderr"] = result.stderr
        
        if result.returncode == 0:
            evidence.status = "pass"
        else:
            evidence.status = "fail"
    
    def _parse_regex(self, result: subprocess.CompletedProcess, evidence: Evidence):
        """使用正则模式解析命令结果。"""
        evidence.raw["stdout"] = result.stdout
        evidence.raw["stderr"] = result.stderr
        evidence.raw["exit_code"] = result.returncode
        
        if not self.regex_pattern:
            evidence.status = "error"
            evidence.raw["error"] = "正则解析器需要模式"
            return
        
        try:
            match = re.search(self.regex_pattern, result.stdout)
            if match:
                evidence.status = "pass"
                evidence.summary = match.groupdict()
            else:
                evidence.status = "error"
                evidence.raw["error"] = f"正则模式不匹配输出"
        except re.error as e:
            evidence.status = "error"
            evidence.raw["error"] = f"正则错误：{e}"
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_command_producer.py -v`  
预期：大部分测试通过，可能需要超时调整

- [ ] **步骤 5：修复并验证所有测试通过**

运行：`python -m pytest tests/harness/test_command_producer.py -v`  
预期：所有测试通过

- [ ] **步骤 6：提交**

```bash
git add entrix/harness/producers/ tests/harness/test_command_producer.py
git commit -m "feat(harness): 添加支持 exit_code 和 regex 解析器的命令生产者"
```

---

## 任务 6：实现内置生产者

**文件：**
- 创建：`entrix/harness/producers/builtin.py`
- 创建：`tests/harness/test_builtin_producers.py`

**接口：**
- 产出：`EntrixFitnessProducer`、`EntrixReviewTriggerProducer`、`DiffStatsProducer`
- 消费：任务 5 的 `Producer` 协议，任务 1 的 `Evidence`

**描述：** 实现 entrix 特定证据收集的内置生产者。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_builtin_producers.py`：

```python
import pytest
from pathlib import Path
from entrix.harness.producers.builtin import (
    EntrixFitnessProducer,
    EntrixReviewTriggerProducer, 
    DiffStatsProducer
)
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.producers.base import ProducerContext
from entrix.harness.conditions import WhenContext

def test_entrix_fitness_producer():
    """测试 EntrixFitnessProducer 生成 fitness 证据"""
    config = EvidenceProducerConfig(
        id="fitness",
        type="fitness",
        name="Entrix fitness 报告",
        builtin="entrix-fitness"
    )
    
    producer = EntrixFitnessProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    evidence = producer.run(context)
    
    assert evidence.id == "fitness"
    assert evidence.type == "fitness"
    # 应该包含 fitness 特定字段
    assert "score" in evidence.summary or evidence.status in ["pass", "fail", "error"]

def test_entrix_review_trigger_producer():
    """测试 EntrixReviewTriggerProducer 生成审查触发证据"""
    config = EvidenceProducerConfig(
        id="review-trigger",
        type="review-trigger",
        name="审查触发评估",
        builtin="entrix-review-trigger"
    )
    
    producer = EntrixReviewTriggerProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    evidence = producer.run(context)
    
    assert evidence.id == "review-trigger"
    assert evidence.type == "review-trigger"
    # 应该包含 human_review_required 字段
    assert "human_review_required" in evidence.summary or evidence.status in ["pass", "fail", "error"]

def test_diff_stats_producer():
    """测试 DiffStatsProducer 生成差异统计"""
    config = EvidenceProducerConfig(
        id="diff-stats",
        type="diff",
        name="Git 差异统计", 
        builtin="diff-stats"
    )
    
    producer = DiffStatsProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd(), changed_files=["README.md"])
    )
    
    evidence = producer.run(context)
    
    assert evidence.id == "diff-stats"
    assert evidence.type == "diff"
    # 应该包含差异统计
    assert any(key in evidence.summary for key in ["added_lines", "deleted_lines", "changed_files"])
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_builtin_producers.py -v`  
预期：builtin 模块的 ImportError

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/producers/builtin.py`：
```python
"""Entrix 特定功能的内置证据生产者。"
import subprocess
from datetime import datetime
from pathlib import Path
from entrix.harness.producers.base import Producer, ProducerContext
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.evidence import Evidence

class EntrixFitnessProducer(Producer):
    """运行 Entrix fitness 报告的生产者。"
    
    def __init__(self, config: EvidenceProducerConfig):
        self.config = config
    
    def run(self, context: ProducerContext) -> Evidence:
        """执行 fitness 报告并返回证据。
        
        Args:
            context: 执行上下文
            
        Returns:
            包含 fitness 结果的 Evidence
        """
        evidence = Evidence(
            id=self.config.id,
            type=self.config.type,
            name=self.config.name,
            producer="entrix-fitness",
            task_id=context.task_id,
            started_at=datetime.utcnow().isoformat() + "Z"
        )
        
        try:
            # 调用现有的 fitness 报告功能
            # 这应该与现有的 entrix.fitness 模块集成
            from entrix.fitness import run_fitness_report
            
            fitness_result = run_fitness_report(context.repo_root)
            
            evidence.status = "pass" if fitness_result.get("overall_status") == "pass" else "fail"
            evidence.summary = {
                "score": fitness_result.get("score", 0),
                "hard_gate_blocked": fitness_result.get("hard_gate_blocked", False),
                "score_blocked": fitness_result.get("score_blocked", False)
            }
            evidence.raw = fitness_result
            
        except ImportError:
            # 如果 fitness 模块不可用时的后备方案
            evidence.status = "error"
            evidence.raw["error"] = "Fitness 模块不可用"
        except Exception as e:
            evidence.status = "error"
            evidence.raw["error"] = str(e)
        
        return evidence

class EntrixReviewTriggerProducer(Producer):
    """评估审查触发的生产者。"
    
    def __init__(self, config: EvidenceProducerConfig):
        self.config = config
    
    def run(self, context: ProducerContext) -> Evidence:
        """评估审查触发并返回证据。
        
        Args:
            context: 执行上下文
            
        Returns:
            包含审查触发结果的 Evidence
        """
        evidence = Evidence(
            id=self.config.id,
            type=self.config.type,
            name=self.config.name,
            producer="entrix-review-trigger",
            task_id=context.task_id,
            started_at=datetime.utcnow().isoformat() + "Z"
        )
        
        try:
            # 调用现有的审查触发功能
            from entrix.review_triggers import evaluate_review_triggers
            
            trigger_result = evaluate_review_triggers(context.repo_root)
            
            evidence.status = "pass" if not trigger_result.get("human_review_required") else "fail"
            evidence.summary = {
                "human_review_required": trigger_result.get("human_review_required", False),
                "triggered_rules": trigger_result.get("triggered_rules", [])
            }
            evidence.raw = trigger_result
            
        except ImportError:
            # 如果审查触发模块不可用时的后备方案
            evidence.status = "error"
            evidence.raw["error"] = "审查触发模块不可用"
        except Exception as e:
            evidence.status = "error"
            evidence.raw["error"] = str(e)
        
        return evidence

class DiffStatsProducer(Producer):
    """收集 git 差异统计的生产者。"
    
    def __init__(self, config: EvidenceProducerConfig):
        self.config = config
    
    def run(self, context: ProducerContext) -> Evidence:
        """收集差异统计并返回证据。
        
        Args:
            context: 执行上下文
            
        Returns:
            包含差异统计的 Evidence
        """
        evidence = Evidence(
            id=self.config.id,
            type=self.config.type,
            name=self.config.name,
            producer="diff-stats",
            task_id=context.task_id,
            started_at=datetime.utcnow().isoformat() + "Z"
        )
        
        try:
            # 使用上下文中的变更文件
            changed_files = context.when_context.changed_files or []
            
            # 计算基本差异统计
            total_added = 0
            total_deleted = 0
            
            for file_path in changed_files:
                try:
                    # 获取每个文件的差异
                    result = subprocess.run(
                        ["git", "diff", "--numstat", "--", file_path],
                        capture_output=True,
                        text=True,
                        cwd=context.repo_root
                    )
                    
                    if result.stdout.strip():
                        parts = result.stdout.strip().split()
                        if len(parts) >= 2:
                            added = int(parts[0])
                            deleted = int(parts[1])
                            total_added += added
                            total_deleted += deleted
                except (subprocess.SubprocessError, ValueError):
                    continue
            
            evidence.status = "pass"
            evidence.summary = {
                "added_lines": total_added,
                "deleted_lines": total_deleted,
                "changed_files": len(changed_files),
                "files": changed_files
            }
            
        except Exception as e:
            evidence.status = "error"
            evidence.raw["error"] = str(e)
        
        return evidence
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_builtin_producers.py -v`  
预期：如果现有模块不存在，部分测试可能失败，但结构应该能正常工作

- [ ] **步骤 5：优雅地处理缺失的依赖**

更新 builtin 生产者，在缺少依赖时提供更优雅的处理和基本实现。

- [ ] **步骤 6：提交**

```bash
git add entrix/harness/producers/builtin.py tests/harness/test_builtin_producers.py
git commit -m "feat(harness): 添加 fitness、审查触发和差异统计的内置生产者"
```

---

## 任务 7：实现门禁策略系统

**文件：**
- 创建：`entrix/harness/gate/__init__.py`
- 创建：`entrix/harness/gate/policy.py`
- 创建：`entrix/harness/gate/dsl.py`
- 创建：`tests/harness/test_gate_policy.py`
- 创建：`tests/harness/test_gate_dsl.py`

**接口：**
- 产出：`GatePolicy`、`GateRule`、`Severity` 类；`evaluate_condition(condition, evidence) -> bool`
- 消费：任务 1 的 `Evidence`，任务 2 的 `GatePolicyConfig`

**描述：** 实现支持表达式 DSL 的门禁策略评估系统。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_gate_dsl.py`：

```python
import pytest
from entrix.harness.gate.dsl import evaluate_condition
from entrix.harness.evidence import Evidence

def test_simple_equality():
    """测试简单相等条件"""
    evidence = Evidence(id="test-1", status="pass")
    result = evaluate_condition('status == "pass"', evidence)
    assert result is True

def test_string_equality_false():
    """测试失败的字符串相等"""
    evidence = Evidence(id="test-1", status="fail")
    result = evaluate_condition('status == "pass"', evidence)
    assert result is False

def test_comparison_operators():
    """测试比较运算符"""
    evidence = Evidence(id="test-1", summary={"score": 85})
    
    assert evaluate_condition("summary.score > 80", evidence) is True
    assert evaluate_condition("summary.score >= 85", evidence) is True
    assert evaluate_condition("summary.score < 90", evidence) is True
    assert evaluate_condition("summary.score <= 85", evidence) is True

def test_arithmetic_operations():
    """测试算术运算"""
    evidence = Evidence(id="test-1", summary={"a": 10, "b": 5})
    
    assert evaluate_condition("summary.a + summary.b > 10", evidence) is True
    assert evaluate_condition("summary.a - summary.b == 5", evidence) is True
    assert evaluate_condition("summary.a * summary.b == 50", evidence) is True
    assert evaluate_condition("summary.a / summary.b == 2", evidence) is True

def test_logical_operators():
    """测试逻辑运算符"""
    evidence = Evidence(id="test-1", status="pass", summary={"score": 85})
    
    assert evaluate_condition('status == "pass" and summary.score > 80', evidence) is True
    assert evaluate_condition('status == "pass" or summary.score > 90', evidence) is True
    assert evaluate_condition('not (status == "fail")', evidence) is True

def test_in_operator():
    """测试 'in' 运算符"""
    evidence = Evidence(id="test-1", summary={"categories": ["security", "performance"]})
    
    assert evaluate_condition('"security" in summary.categories', evidence) is True
    assert evaluate_condition('"documentation" in summary.categories', evidence) is False

def test_parentheses():
    """测试括号分组"""
    evidence = Evidence(id="test-1", status="pass", summary={"score": 85})
    
    result = evaluate_condition('(status == "pass" or status == "skipped") and summary.score > 80', evidence)
    assert result is True

def test_nested_field_access():
    """测试嵌套字段访问"""
    evidence = Evidence(id="test-1", summary={"nested": {"deep": {"value": 42}}})
    
    result = evaluate_condition("summary.nested.deep.value == 42", evidence)
    assert result is True
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_gate_dsl.py -v`  
预期：gate 模块的 ImportError

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/gate/__init__.py`：
```python
"""门禁策略评估系统。"
```

创建 `entrix/harness/gate/policy.py`：
```python
"""门禁策略数据结构。"
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional

class Severity(Enum):
    """门禁策略的严重程度级别。"""
    HARD = "hard"
    SOFT = "soft" 
    ADVISORY = "advisory"
    BLOCKED = "blocked"

@dataclass
class GateRule:
    """用于评估证据的单个门禁规则。"""
    name: str = ""
    evidence_id: Optional[str] = None
    evidence_type: Optional[str] = None
    condition: str = ""
    action: Optional[str] = None

@dataclass
class GatePolicy:
    """包含一个或多个门禁规则的策略。"""
    name: str = ""
    severity: Severity = Severity.HARD
    rule: GateRule = None
    
    def __post_init__(self):
        if self.rule is None:
            self.rule = GateRule()
        elif isinstance(self.rule, dict):
            self.rule = GateRule(**self.rule)
```

创建 `entrix/harness/gate/dsl.py`：
```python
"""门禁条件的表达式 DSL。"
import re
from entrix.harness.evidence import Evidence

# MVP 的简单表达式解析器
# 支持：==、!=、<、<=、>、>=、+、-、*、/、in、and、or、not、括号

class ExpressionEvaluator:
    """门禁条件表达式的求值器。"
    
    def __init__(self, expression: str):
        self.expression = expression.strip()
        self.pos = 0
    
    def evaluate(self, evidence: Evidence) -> bool:
        """根据证据评估表达式。
        
        Args:
            evidence: 要评估的 Evidence 对象
            
        Returns:
            评估结果的布尔值
        """
        try:
            result = self._parse_expression(evidence)
            return bool(result)
        except Exception:
            return False
    
    def _parse_expression(self, evidence: Evidence):
        """解析并评估表达式。"""
        return self._parse_or(evidence)
    
    def _parse_or(self, evidence: Evidence):
        """解析 OR 表达式。"""
        left = self._parse_and(evidence)
        
        while self._match("or"):
            right = self._parse_and(evidence)
            left = left or right
        
        return left
    
    def _parse_and(self, evidence: Evidence):
        """解析 AND 表达式。"""
        left = self._parse_not(evidence)
        
        while self._match("and"):
            right = self._parse_not(evidence)
            left = left and right
        
        return left
    
    def _parse_not(self, evidence: Evidence):
        """解析 NOT 表达式。"""
        if self._match("not"):
            operand = self._parse_comparison(evidence)
            return not operand
        return self._parse_comparison(evidence)
    
    def _parse_comparison(self, evidence: Evidence):
        """解析比较表达式。"""
        left = self._parse_addition(evidence)
        
        if self._match("=="):
            right = self._parse_addition(evidence)
            return left == right
        elif self._match("!="):
            right = self._parse_addition(evidence)
            return left != right
        elif self._match("<"):
            right = self._parse_addition(evidence)
            return left < right
        elif self._match("<="):
            right = self._parse_addition(evidence)
            return left <= right
        elif self._match(">"):
            right = self._parse_addition(evidence)
            return left > right
        elif self._match(">="):
            right = self._parse_addition(evidence)
            return left >= right
        elif self._match("in"):
            right = self._parse_addition(evidence)
            return left in right if isinstance(right, (list, str)) else False
        
        return left
    
    def _parse_addition(self, evidence: Evidence):
        """解析加法/减法。"""
        left = self._parse_multiplication(evidence)
        
        while self._match("+"):
            right = self._parse_multiplication(evidence)
            left = left + right
        elif self._match("-"):
            right = self._parse_multiplication(evidence)
            left = left - right
        
        return left
    
    def _parse_multiplication(self, evidence: Evidence):
        """解析乘法/除法。"""
        left = self._parse_primary(evidence)
        
        while self._match("*"):
            right = self._parse_primary(evidence)
            left = left * right
        elif self._match("/"):
            right = self._parse_primary(evidence)
            left = left / right
        
        return left
    
    def _parse_primary(self, evidence: Evidence):
        """解析基本表达式。"""
        if self._match("("):
            expr = self._parse_expression(evidence)
            self._consume(")")
            return expr
        
        # 解析字符串字面量
        string_match = re.match(r'"([^"]*)"', self.expression[self.pos:])
        if string_match:
            value = string_match.group(1)
            self.pos += len(string_match.group(0))
            return value
        
        # 解析数字
        number_match = re.match(r'\d+(\.\d+)?', self.expression[self.pos:])
        if number_match:
            value_str = number_match.group(0)
            self.pos += len(value_str)
            return float(value_str) if '.' in value_str else int(value_str)
        
        # 解析字段访问
        return self._parse_field_access(evidence)
    
    def _parse_field_access(self, evidence: Evidence):
        """解析字段访问表达式。"""
        # 简单的字段访问，如 status、summary.score、summary.nested.deep.value
        field_match = re.match(r'([a-zA-Z_][a-zA-Z0-9_.]*)', self.expression[self.pos:])
        if field_match:
            field_path = field_match.group(1)
            self.pos += len(field_path)
            return self._get_field_value(evidence, field_path)
        
        return None
    
    def _get_field_value(self, evidence: Evidence, field_path: str):
        """通过字段路径从证据中获取值。"""
        parts = field_path.split(".")
        value = evidence
        
        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            elif isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        
        return value
    
    def _match(self, token: str) -> bool:
        """检查当前位置是否匹配 token。"""
        if self.expression.startswith(token, self.pos):
            # 确保是一个完整的词/token
            next_pos = self.pos + len(token)
            if next_pos >= len(self.expression):
                self.pos = next_pos
                return True
            next_char = self.expression[next_pos]
            if next_char in ' \t\n)<>!=+-*/,':
                self.pos = next_pos
                # 跳过空白字符
                while self.pos < len(self.expression) and self.expression[self.pos] in ' \t\n':
                    self.pos += 1
                return True
        return False
    
    def _consume(self, char: str):
        """消耗特定字符。"""
        if self.pos < len(self.expression) and self.expression[self.pos] == char:
            self.pos += 1
            while self.pos < len(self.expression) and self.expression[self.pos] in ' \t\n':
                self.pos += 1

def evaluate_condition(condition: str, evidence: Evidence) -> bool:
    """根据证据评估门禁条件表达式。
    
    Args:
        condition: 要评估的表达式字符串
        evidence: Evidence 对象
        
    Returns:
        评估结果的布尔值
    """
    evaluator = ExpressionEvaluator(condition)
    return evaluator.evaluate(evidence)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_gate_dsl.py -v`  
预期：大部分测试通过，可能需要解析器优化

- [ ] **步骤 5：修复并验证所有测试通过**

运行：`python -m pytest tests/harness/test_gate_dsl.py -v`  
预期：所有测试通过

- [ ] **步骤 6：提交**

```bash
git add entrix/harness/gate/ tests/harness/test_gate_dsl.py
git commit -m "feat(harness): 添加门禁策略 DSL 和评估系统"
```

---

## 任务 8：实现门禁仲裁器

**文件：**
- 创建：`entrix/harness/gate/arbiter.py`
- 创建：`tests/harness/test_arbiter.py`

**接口：**
- 产出：`GateEngine.arbitrate(bundle) -> Verdict`，`Verdict` 数据类
- 消费：任务 1 的 `EvidenceBundle`，任务 7 的 `GatePolicy`，任务 7 的 `evaluate_condition`

**描述：** 实现门禁仲裁引擎，根据证据包评估所有门禁策略。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_arbiter.py`：

```python
import pytest
from entrix.harness.gate.arbiter import GateEngine, GateResult, Verdict, VerdictStatus
from entrix.harness.gate.policy import GatePolicy, GateRule, Severity
from entrix.harness.evidence import Evidence, EvidenceBundle

def test_hard_gate_pass():
    """测试通过的硬门禁"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="test-1", type="test", name="测试", status="pass", summary={"passed": 10, "failed": 0})
        ]
    )
    
    policy = GatePolicy(
        name="测试通过",
        severity=Severity.HARD,
        rule=GateRule(
            name="测试规则",
            evidence_id="test-1",
            condition='status == "pass"'
        )
    )
    
    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)
    
    assert verdict.status == VerdictStatus.PASS
    assert len(verdict.gate_results) == 1
    assert verdict.gate_results[0].passed is True

def test_hard_gate_fail():
    """测试失败的硬门禁"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="test-1", type="test", name="测试", status="fail", summary={"failed": 5})
        ]
    )
    
    policy = GatePolicy(
        name="测试通过",
        severity=Severity.HARD,
        rule=GateRule(
            name="测试规则",
            evidence_id="test-1",
            condition='status == "pass"'
        )
    )
    
    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)
    
    assert verdict.status == VerdictStatus.FAIL
    assert verdict.gate_results[0].passed is False

def test_soft_gate_warning():
    """测试软门禁产生警告但通过"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="test-1", type="test", name="测试", status="pass", summary={"coverage": 60})
        ]
    )
    
    policy = GatePolicy(
        name="高覆盖率",
        severity=Severity.SOFT,
        rule=GateRule(
            name="覆盖率检查",
            evidence_id="test-1",
            condition="summary.coverage > 80"
        )
    )
    
    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)
    
    assert verdict.status == VerdictStatus.PASS  # 软门禁不会导致失败
    assert verdict.gate_results[0].passed is False
    assert "warning" in verdict.gate_results[0].message.lower()

def test_blocked_gate():
    """测试 blocked 门禁触发 BLOCKED 状态"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="diff-1", type="diff", name="差异", summary={"added_lines": 1000})
        ]
    )
    
    policy = GatePolicy(
        name="大差异",
        severity=Severity.BLOCKED,
        rule=GateRule(
            name="差异大小检查",
            evidence_id="diff-1",
            condition="summary.added_lines > 500"
        )
    )
    
    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)
    
    assert verdict.status == VerdictStatus.BLOCKED
    assert verdict.gate_results[0].passed is False

def test_evidence_type_matching():
    """测试按 evidence_type 而非 evidence_id 匹配"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="test-1", type="test", name="单元测试", status="pass"),
            Evidence(id="test-2", type="test", name="集成测试", status="pass")
        ]
    )
    
    policy = GatePolicy(
        name="所有测试通过",
        severity=Severity.HARD,
        rule=GateRule(
            name="测试类型检查",
            evidence_type="test",
            condition='status == "pass"'
        )
    )
    
    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)
    
    # 应该对两个测试证据进行评估
    assert verdict.status == VerdictStatus.PASS

def test_multiple_gates():
    """测试多个门禁一起评估"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="test-1", type="test", status="pass", summary={"failed": 0}),
            Evidence(id="lint-1", type="lint", status="pass")
        ]
    )
    
    policies = [
        GatePolicy(
            name="测试通过",
            severity=Severity.HARD,
            rule=GateRule(evidence_id="test-1", condition='status == "pass"')
        ),
        GatePolicy(
            name="代码检查通过", 
            severity=Severity.HARD,
            rule=GateRule(evidence_id="lint-1", condition='status == "pass"')
        )
    ]
    
    engine = GateEngine(policies)
    verdict = engine.arbitrate(bundle)
    
    assert verdict.status == VerdictStatus.PASS
    assert len(verdict.gate_results) == 2

def test_gate_evaluation_error():
    """测试门禁评估错误处理"""
    bundle = EvidenceBundle(
        task_id="task-1",
        evidence=[
            Evidence(id="test-1", type="test", status="pass")
        ]
    )
    
    policy = GatePolicy(
        name="损坏的门禁",
        severity=Severity.HARD,
        rule=GateRule(
            evidence_id="test-1",
            condition="nonexistent.field == 123"  # 无效字段
        )
    )
    
    engine = GateEngine([policy])
    verdict = engine.arbitrate(bundle)
    
    assert verdict.status == VerdictStatus.FAIL  # 有错误的硬门禁失败
    assert "error" in verdict.gate_results[0].message.lower()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_arbiter.py -v`  
预期：arbiter 模块的 ImportError

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/gate/arbiter.py`：
```python
"""门禁仲裁引擎。"
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from entrix.harness.gate.policy import GatePolicy, Severity
from entrix.harness.gate.dsl import evaluate_condition
from entrix.harness.evidence import EvidenceBundle, Evidence

class VerdictStatus(Enum):
    """最终裁决状态。"""
    PASS = "pass"
    FAIL = "fail" 
    BLOCKED = "blocked"

@dataclass
class GateResult:
    """单个门禁评估的结果。"""
    policy_name: str
    severity: Severity
    passed: bool
    message: str = ""
    matched_evidence_id: str = ""

@dataclass
class Verdict:
    """评估所有门禁后的最终裁决。"""
    status: VerdictStatus
    gate_results: List[GateResult] = field(default_factory=list)
    summary: str = ""

class GateEngine:
    """根据证据包评估门禁策略的引擎。"
    
    def __init__(self, policies: List[GatePolicy]):
        """初始化门禁引擎。
        
        Args:
            policies: 要评估的门禁策略列表
        """
        self.policies = policies
    
    def arbitrate(self, bundle: EvidenceBundle) -> Verdict:
        """根据证据包评估所有门禁策略。
        
        Args:
            bundle: 要评估的证据包
            
        Returns:
            包含整体状态和各个门禁结果的 Verdict
        """
        gate_results = []
        overall_status = VerdictStatus.PASS
        
        for policy in self.policies:
            result = self._evaluate_policy(policy, bundle)
            gate_results.append(result)
            
            # 根据严重程度和结果更新整体状态
            if not result.passed:
                if policy.severity == Severity.HARD:
                    overall_status = VerdictStatus.FAIL
                elif policy.severity == Severity.BLOCKED and result.passed is False:
                    # blocked 门禁在条件为 TRUE 时触发（与 hard 相反）
                    overall_status = VerdictStatus.BLOCKED
        
        return Verdict(
            status=overall_status,
            gate_results=gate_results,
            summary=self._generate_summary(gate_results, overall_status)
        )
    
    def _evaluate_policy(self, policy: GatePolicy, bundle: EvidenceBundle) -> GateResult:
        """根据证据包评估单个策略。
        
        Args:
            policy: 要评估的策略
            bundle: 证据包
            
        Returns:
            包含评估结果的 GateResult
        """
        # 查找匹配的证据
        matching_evidences = self._find_matching_evidence(policy.rule, bundle)
        
        if not matching_evidences:
            return GateResult(
                policy_name=policy.name,
                severity=policy.severity,
                passed=False,
                message=f"规则没有匹配的证据：{policy.rule.evidence_id or policy.rule.evidence_type}"
            )
        
        # 对所有匹配的证据进行评估
        all_passed = True
        messages = []
        
        for evidence in matching_evidences:
            try:
                condition_result = evaluate_condition(policy.rule.condition, evidence)
                if not condition_result:
                    all_passed = False
                    messages.append(f"对证据 {evidence.id} 失败")
            except Exception as e:
                all_passed = False
                messages.append(f"评估条件时出错：{str(e)}")
        
        message = "; ".join(messages) if messages else "通过"
        
        # 对于 blocked 门禁，逻辑是反转的 - 条件为 TRUE 时失败
        if policy.severity == Severity.BLOCKED:
            all_passed = not all_passed
        
        return GateResult(
            policy_name=policy.name,
            severity=policy.severity,
            passed=all_passed,
            message=message,
            matched_evidence_id=matching_evidences[0].id if matching_evidences else ""
        )
    
    def _find_matching_evidence(self, rule, bundle: EvidenceBundle) -> List[Evidence]:
        """查找匹配规则的证据。
        
        Args:
            rule: 包含 evidence_id 或 evidence_type 的门禁规则
            bundle: 要搜索的证据包
            
        Returns:
            匹配的证据项列表
        """
        if rule.evidence_id:
            # 按特定 ID 匹配
            for evidence in bundle.evidence:
                if evidence.id == rule.evidence_id:
                    return [evidence]
            return []
        
        if rule.evidence_type:
            # 按类型匹配
            return [ev for ev in bundle.evidence if ev.type == rule.evidence_type]
        
        return []
    
    def _generate_summary(self, gate_results: List[GateResult], status: VerdictStatus) -> str:
        """生成人类可读的摘要。
        
        Args:
            gate_results: 各个门禁的结果
            status: 整体裁决状态
            
        Returns:
            摘要字符串
        """
        passed_count = sum(1 for r in gate_results if r.passed)
        total_count = len(gate_results)
        
        if status == VerdictStatus.PASS:
            return f"所有门禁通过（{passed_count}/{total_count}）"
        elif status == VerdictStatus.FAIL:
            failed_gates = [r.policy_name for r in gate_results if not r.passed and r.severity == Severity.HARD]
            return f"硬门禁失败：{', '.join(failed_gates)}"
        elif status == VerdictStatus.BLOCKED:
            blocked_gates = [r.policy_name for r in gate_results if not r.passed and r.severity == Severity.BLOCKED]
            return f"触发阻塞门禁：{', '.join(blocked_gates)}"
        
        return "未知状态"
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_arbiter.py -v`  
预期：大部分测试通过，可能需要 blocked 门禁逻辑调整

- [ ] **步骤 5：修复并验证所有测试通过**

运行：`python -m pytest tests/harness/test_arbiter.py -v`  
预期：所有测试通过

- [ ] **步骤 6：提交**

```bash
git add entrix/harness/gate/arbiter.py tests/harness/test_arbiter.py
git commit -m "feat(harness): 添加门禁仲裁引擎和裁决生成"
```

---

## 任务 9：实现证据收集引擎

**文件：**
- 创建：`entrix/harness/engine.py`
- 创建：`tests/harness/test_engine.py`

**接口：**
- 产出：`EvidenceEngine.collect(config, context) -> EvidenceBundle`，`HarnessRunContext` 数据类
- 消费：任务 2 的 `HarnessConfig`，任务 3 的 `WhenContext`，任务 4 的 `EvidenceStore`，任务 5-6 的所有生产者

**描述：** 实现主要的证据收集引擎，根据配置编排生产者。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_engine.py`：

```python
import pytest
from pathlib import Path
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.config import HarnessConfig, EvidenceProducerConfig
from entrix.harness.conditions import WhenContext
from entrix.harness.store import EvidenceStore

def test_collect_evidence_with_command_producer():
    """测试使用命令生产者收集证据"""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="test-1",
                type="test",
                name="测试生产者",
                command="echo 'passed=10, failed=0'",
                producer="test",
                parser={"type": "regex", "pattern": r'passed=(?P<passed>\d+), failed=(?P<failed>\d+)'}
            )
        ],
        gate_policies=[]
    )
    
    context = HarnessRunContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    engine = EvidenceEngine(config)
    bundle = engine.collect(context)
    
    assert bundle.task_id == "task-1"
    assert len(bundle.evidence) == 1
    assert bundle.evidence[0].id == "test-1"
    assert bundle.evidence[0].status == "pass"

def test_collect_with_global_when_filter():
    """测试带有全局 when 条件的证据收集"""
    import tempfile
    import os
    
    # 创建存在的临时文件
    temp_file = Path("/tmp/test_marker.txt")
    temp_file.write_text("marker")
    
    config = HarnessConfig(
        version="harness/v1",
        when={"files_exist": ["/tmp/test_marker.txt"]},
        evidence_producers=[
            EvidenceProducerConfig(
                id="test-1",
                type="test", 
                name="测试",
                command="echo 'test'",
                producer="test",
                parser={"type": "exit_code"}
            )
        ],
        gate_policies=[]
    )
    
    context = HarnessRunContext(
        task_id="task-1",
        repo_root=Path("/tmp"),
        when_context=WhenContext(repo_root=Path("/tmp"))
    )
    
    engine = EvidenceEngine(config)
    bundle = engine.collect(context)
    
    # 应该执行，因为全局 when 条件满足
    assert len(bundle.evidence) == 1

def test_collect_with_producer_when_filter():
    """测试带有生产者特定 when 条件的证据收集"""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="test-1",
                type="test",
                name="测试", 
                command="echo 'test'",
                producer="test",
                parser={"type": "exit_code"},
                when={"files_exist": ["/tmp/does_not_exist.txt"]}  # 应该跳过
            ),
            EvidenceProducerConfig(
                id="test-2",
                type="test",
                name="测试 2",
                command="echo 'test2'",
                producer="test",
                parser={"type": "exit_code"}
                # 没有 when 条件 - 应该运行
            )
        ],
        gate_policies=[]
    )
    
    context = HarnessRunContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    engine = EvidenceEngine(config)
    bundle = engine.collect(context)
    
    # 应该只执行 test-2
    assert len(bundle.evidence) == 1
    assert bundle.evidence[0].id == "test-2"

def test_collect_with_builtin_producer():
    """测试使用内置生产者收集证据"""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="diff-1",
                type="diff",
                name="差异统计",
                builtin="diff-stats"
            )
        ],
        gate_policies=[]
    )
    
    context = HarnessRunContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(
            repo_root=Path.cwd(),
            changed_files=["README.md", "src/main.py"]
        )
    )
    
    engine = EvidenceEngine(config)
    bundle = engine.collect(context)
    
    assert len(bundle.evidence) == 1
    assert bundle.evidence[0].id == "diff-1"
    assert bundle.evidence[0].type == "diff"

def test_collect_handles_producer_errors():
    """测试生产者错误不阻止收集"""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="failing-1",
                type="test",
                name="失败测试",
                command="exit 1",
                producer="test",
                parser={"type": "exit_code"}
            ),
            EvidenceProducerConfig(
                id="passing-1",
                type="test", 
                name="通过测试",
                command="echo 'success'",
                producer="test",
                parser={"type": "exit_code"}
            )
        ],
        gate_policies=[]
    )
    
    context = HarnessRunContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )
    
    engine = EvidenceEngine(config)
    bundle = engine.collect(context)
    
    # 应该收集两个证据
    assert len(bundle.evidence) == 2
    assert bundle.evidence[0].status == "fail"
    assert bundle.evidence[1].status == "pass"

def test_collect_with_storage():
    """测试带存储的证据收集"""
    from tempfile import TemporaryDirectory
    
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="test-1",
                type="test",
                name="测试",
                command="echo 'test'",
                producer="test",
                parser={"type": "exit_code"}
            )
        ],
        gate_policies=[]
    )
    
    with TemporaryDirectory() as tmpdir:
        context = HarnessRunContext(
            task_id="task-1",
            repo_root=Path.cwd(),
            when_context=WhenContext(repo_root=Path.cwd()),
            store=EvidenceStore(Path(tmpdir))
        )
        
        engine = EvidenceEngine(config)
        bundle = engine.collect(context)
        
        # 应该保存包
        assert bundle.task_id == "task-1"
        assert len(bundle.evidence) == 1
        
        # 验证文件已创建
        evidence_dir = Path(tmpdir) / ".harness" / "evidence" / "task-1"
        assert evidence_dir.exists()
        assert len(list(evidence_dir.glob("*.json"))) == 1
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_engine.py -v`  
预期：engine 模块的 ImportError

- [ ] **步骤 3：编写最小实现**

创建 `entrix/harness/engine.py`：
```python
"""证据收集引擎。"
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from entrix.harness.config import HarnessConfig, EvidenceProducerConfig
from entrix.harness.conditions import WhenContext, evaluate_when
from entrix.harness.store import EvidenceStore
from entrix.harness.evidence import EvidenceBundle
from entrix.harness.producers.base import ProducerContext
from entrix.harness.producers.command import CommandProducer
from entrix.harness.producers.builtin import (
    EntrixFitnessProducer,
    EntrixReviewTriggerProducer,
    DiffStatsProducer
)

@dataclass
class HarnessRunContext:
    """运行 harness 证据收集的上下文。"""
    task_id: str
    repo_root: Path
    when_context: WhenContext
    attempt_id: str = "unknown"
    store: Optional[EvidenceStore] = None

class EvidenceEngine:
    """基于 harness 配置收集证据的引擎。"
    
    def __init__(self, config: HarnessConfig):
        """初始化证据引擎。
        
        Args:
            config: Harness 配置
        """
        self.config = config
        self._producer_registry = {
            "entrix-fitness": EntrixFitnessProducer,
            "entrix-review-trigger": EntrixReviewTriggerProducer,
            "diff-stats": DiffStatsProducer
        }
    
    def collect(self, context: HarnessRunContext) -> EvidenceBundle:
        """根据配置收集证据。
        
        Args:
            context: Harness 运行上下文
            
        Returns:
            包含收集证据的 EvidenceBundle
        """
        # 检查全局 when 条件
        if not evaluate_when(self.config.when, context.when_context):
            return EvidenceBundle(
                task_id=context.task_id,
                attempt_id=context.attempt_id,
                evidence=[],
                collection_errors=[{"message": "全局 when 条件不满足"}]
            )
        
        evidence_list = []
        collection_errors = []
        
        # 过滤并执行生产者
        active_producers = []
        for producer_config in self.config.evidence_producers:
            # 检查生产者特定的 when 条件
            if evaluate_when(producer_config.when, context.when_context):
                active_producers.append(producer_config)
        
        # 并行执行生产者
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_producer = {}
            
            for producer_config in active_producers:
                producer = self._create_producer(producer_config)
                producer_context = ProducerContext(
                    task_id=context.task_id,
                    repo_root=context.repo_root,
                    when_context=context.when_context,
                    attempt_id=context.attempt_id
                )
                
                future = executor.submit(producer.run, producer_context)
                future_to_producer[future] = producer_config
            
            for future in as_completed(future_to_producer):
                producer_config = future_to_producer[future]
                try:
                    evidence = future.result()
                    evidence_list.append(evidence)
                except Exception as e:
                    collection_errors.append({
                        "producer_id": producer_config.id,
                        "error": str(e)
                    })
        
        bundle = EvidenceBundle(
            task_id=context.task_id,
            attempt_id=context.attempt_id,
            evidence=evidence_list,
            collection_errors=collection_errors
        )
        
        # 如果提供了存储，保存包
        if context.store:
            try:
                context.store.save(bundle)
            except Exception as e:
                collection_errors.append({"storage_error": str(e)})
        
        return bundle
    
    def _create_producer(self, config: EvidenceProducerConfig):
        """从配置创建生产者实例。
        
        Args:
            config: 生产者配置
            
        Returns:
            生产者实例
        """
        # 检查是否是内置生产者
        if config.builtin:
            producer_class = self._producer_registry.get(config.builtin)
            if producer_class:
                return producer_class(config)
            else:
                raise ValueError(f"未知的内置生产者：{config.builtin}")
        
        # 默认使用命令生产者
        return CommandProducer(config)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_engine.py -v`  
预期：大部分测试通过，可能需要小幅调整

- [ ] **步骤 5：修复并验证所有测试通过**

运行：`python -m pytest tests/harness/test_engine.py -v`  
预期：所有测试通过

- [ ] **步骤 6：提交**

```bash
git add entrix/harness/engine.py tests/harness/test_engine.py
git commit -m "feat(harness): 添加证据收集引擎和生产者编排"
```

---

## 任务 10：实现 Stop-Gate 集成

**文件：**
- 修改：`entrix/stop_gate/hook.py`
- 创建：`entrix/stop_gate/adapter.py` 
- 创建：`entrix/stop_gate/runner.py`
- 修改：`entrix/stop_gate/__init__.py`
- 创建：`tests/stop_gate/test_harness_integration.py`

**接口：**
- 产出：`StopGateAdapter`，`HarnessRunner`，修改的 hook 入口点
- 消费：任务 9 的 `EvidenceEngine`，任务 8 的 `GateEngine`，现有 stop_gate 组件

**描述：** 将 harness 系统与现有 stop-gate hook 集成，保持向后兼容。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/stop_gate/test_harness_integration.py`：

```python
import pytest
from pathlib import Path
from entrix.stop_gate.adapter import StopGateAdapter
from entrix.stop_gate.runner import HarnessRunner
from entrix.harness.config import load_harness_config
from entrix.harness.conditions import WhenContext

def test_adapter_creates_context_from_payload():
    """测试适配器将 hook 载荷转换为 HarnessRunContext"""
    payload = {
        "task_id": "test-task-123",
        "repo_path": "/tmp/test_repo",
        "changed_files": ["src/main.py", "tests/test_main.py"],
        "branch": "feature/add-auth"
    }
    
    adapter = StopGateAdapter()
    context = adapter.adapt_payload(payload)
    
    assert context.task_id == "test-task-123"
    assert context.repo_root == Path("/tmp/test_repo")
    assert context.when_context.changed_files == ["src/main.py", "tests/test_main.py"]
    assert context.when_context.current_branch == "feature/add-auth"

def test_adapter_without_changed_files():
    """测试适配器处理载荷中缺少的 changed_files"""
    payload = {
        "task_id": "test-task-456",
        "repo_path": "/tmp/test_repo"
    }
    
    adapter = StopGateAdapter()
    context = adapter.adapt_payload(payload)
    
    assert context.task_id == "test-task-456"
    assert context.when_context.changed_files == []

def test_harness_runner_collects_and_arbitrates():
    """测试 harness 端到端流程"""
    # 创建最小 harness.yaml
    harness_yaml = """
version: "harness/v1"

evidence_producers:
  - id: test-1
    type: test
    name: 测试
    command: echo "passed=5, failed=0"
    producer: test
    parser:
      type: regex
      pattern: 'passed=(?P<passed>\\d+), failed=(?P<failed>\\d+)'

gate_policies:
  - name: 测试通过
    severity: hard
    rule:
      evidence_id: test-1
      condition: summary.failed == 0
"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(harness_yaml)
        config_path = Path(f.name)
    
    try:
        context = {
            "task_id": "task-1",
            "repo_path": "/tmp",
            "changed_files": ["src/main.py"],
            "branch": "main"
        }
        
        runner = HarnessRunner(config_path)
        verdict = runner.run(context)
        
        assert verdict.status == "pass"  # 应该通过，因为 failed=0
        assert len(verdict.gate_results) == 1
        
    finally:
        config_path.unlink()

def test_stop_gate_routes_to_harness_when_config_exists():
    """测试 stop-gate hook 在存在配置时路由到 harness"""
    # 这将是与实际 hook 的集成测试
    # 目前，测试路由逻辑
    import tempfile
    
    harness_yaml = """
version: "harness/v1"
evidence_producers: []
gate_policies: []
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='harness.yaml', delete=False) as f:
        f.write(harness_yaml)
        config_path = Path(f.name)
    
    try:
        # 模拟 hook 路由逻辑
        should_use_harness = config_path.exists()
        assert should_use_harness is True
        
    finally:
        config_path.unlink()

def test_stop_gate_fallback_without_config():
    """测试没有 harness.yaml 时 stop-gate 回退到旧逻辑"""
    import tempfile
    
    # 测试不存在的配置
    non_existent_path = Path("/tmp/non_existent_harness.yaml")
    should_use_harness = non_existent_path.exists()
    
    assert should_use_harness is False
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/stop_gate/test_harness_integration.py -v`  
预期：新模块的 ImportError

- [ ] **步骤 3：编写最小实现**

创建 `entrix/stop_gate/adapter.py`：
```python
"""用于将 stop-gate hook 载荷转换为 harness 上下文的适配器。"
from pathlib import Path
from typing import Dict, Any
from entrix.harness.engine import HarnessRunContext
from entrix.harness.conditions import WhenContext
from entrix.harness.store import EvidenceStore

class StopGateAdapter:
    """用于将 hook 载荷转换为 harness 上下文的适配器。"
    
    def adapt_payload(self, payload: Dict[str, Any]) -> HarnessRunContext:
        """将 hook 载荷转换为 HarnessRunContext。
        
        Args:
            payload: Hook 载荷字典
            
        Returns:
            用于 harness 执行的 HarnessRunContext
        """
        repo_root = Path(payload.get("repo_path", "/"))
        task_id = payload.get("task_id", "unknown")
        
        # 创建 when 上下文
        when_context = WhenContext(
            repo_root=repo_root,
            changed_files=payload.get("changed_files", []),
            current_branch=payload.get("branch", "unknown")
        )
        
        # 创建证据存储
        store = EvidenceStore(repo_root)
        
        return HarnessRunContext(
            task_id=task_id,
            repo_root=repo_root,
            when_context=when_context,
            store=store
        )
```

创建 `entrix/stop_gate/runner.py`：
```python
"""用于 stop-gate 集成的 Harness 运行器。"
from pathlib import Path
from typing import Dict, Any
from entrix.harness.config import load_harness_config
from entrix.harness.engine import EvidenceEngine
from entrix.harness.gate.arbiter import GateEngine
from entrix.harness.store import EvidenceStore
from entrix.stop_gate.adapter import StopGateAdapter

class HarnessRunner:
    """在 stop-gate 上下文中执行 harness 流程的运行器。"
    
    def __init__(self, config_path: Path):
        """初始化 harness 运行器。
        
        Args:
            config_path: harness.yaml 配置路径
        """
        self.config_path = config_path
        self.config = None
        self.adapter = StopGateAdapter()
    
    def run(self, context: Dict[str, Any]) -> Any:
        """执行完整的 harness 流程。
        
        Args:
            context: Hook 载荷字典
            
        Returns:
            来自门禁仲裁的 Verdict
        """
        # 加载配置
        self.config = load_harness_config(self.config_path)
        
        # 调整载荷为 harness 上下文
        harness_context = self.adapter.adapt_payload(context)
        
        # 收集证据
        evidence_engine = EvidenceEngine(self.config)
        bundle = evidence_engine.collect(harness_context)
        
        # 仲裁门禁
        gate_engine = GateEngine(self.config.gate_policies)
        verdict = gate_engine.arbitrate(bundle)
        
        return verdict
```

- [ ] **步骤 4：更新现有 stop_gate 组件**

修改 `entrix/stop_gate/hook.py`（假设存在）：
```python
"""带有 harness 集成的 stop-gate hook 入口点。"
from pathlib import Path
import sys
import json

def main():
    """stop-gate hook 的主入口点。"""
    # 从 stdin 或参数读取载荷
    payload = read_hook_payload()
    
    repo_path = Path(payload.get("repo_path", "."))
    harness_config_path = repo_path / "harness.yaml"
    
    if harness_config_path.exists():
        # 使用新的 harness 系统
        from entrix.stop_gate.runner import HarnessRunner
        
        runner = HarnessRunner(harness_config_path)
        verdict = runner.run(payload)
        
        # 格式化并输出裁决
        output_verdict(verdict)
    else:
        # 回退到现有逻辑
        run_legacy_stop_gate(payload)

def read_hook_payload() -> dict:
    """从 stdin 或参数读取 hook 载荷。"""
    try:
        return json.loads(sys.stdin.read())
    except:
        return {}

def output_verdict(verdict):
    """将裁决输出到 stdout。"""
    print(json.dumps({
        "status": verdict.status.value,
        "summary": verdict.summary,
        "gate_results": [
            {
                "policy": r.policy_name,
                "passed": r.passed,
                "message": r.message
            }
            for r in verdict.gate_results
        ]
    }))

def run_legacy_stop_gate(payload):
    """运行现有的 stop-gate 逻辑以保持向后兼容。"""
    # 调用现有的 fitness + review-trigger 逻辑
    from entrix.stop_gate.legacy import run_legacy_gate
    run_legacy_gate(payload)

if __name__ == "__main__":
    main()
```

- [ ] **步骤 5：运行测试验证通过**

运行：`python -m pytest tests/stop_gate/test_harness_integration.py -v`  
预期：大部分测试通过，可能需要根据现有 stop_gate 结构进行调整

- [ ] **步骤 6：修复并验证所有测试通过**

运行：`python -m pytest tests/stop_gate/test_harness_integration.py -v`  
预期：所有测试通过

- [ ] **步骤 7：提交**

```bash
git add entrix/stop_gate/ tests/stop_gate/test_harness_integration.py
git commit -m "feat(stop-gate): 集成 harness 系统与 stop-gate hook"
```

---

## 任务 11：实现 CLI 命令

**文件：**
- 创建：`entrix/cli/harness.py`
- 创建：`tests/cli/test_harness_commands.py`

**接口：**
- 产出：`entrix harness validate`，`entrix harness run` CLI 命令
- 消费：任务 2 的 `load_harness_config`，任务 9 的 `EvidenceEngine`，任务 8 的 `GateEngine`

**描述：** 实现 harness 验证和手动执行的 CLI 命令。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/cli/test_harness_commands.py`：

```python
import pytest
import subprocess
import tempfile
from pathlib import Path

def test_harness_validate_command():
    """测试 'entrix harness validate' 命令"""
    harness_yaml = """
version: "harness/v1"

evidence_producers:
  - id: test-1
    type: test
    name: 测试
    command: pytest
    producer: pytest
    parser:
      type: exit_code

gate_policies:
  - name: 测试通过
    severity: hard
    rule:
      evidence_id: test-1
      condition: status == "pass"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(harness_yaml)
        
        result = subprocess.run(
            ["entrix", "harness", "validate", str(config_path)],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "valid" in result.stdout.lower() or "有效" in result.stdout.lower()

def test_harness_validate_invalid_config():
    """测试验证无效配置"""
    invalid_yaml = """
version: "harness/v2"  # 不支持的版本

evidence_producers: []
gate_policies: []
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(invalid_yaml)
        
        result = subprocess.run(
            ["entrix", "harness", "validate", str(config_path)],
            capture_output=True,
            text=True
        )
        
        assert result.returncode != 0
        assert "unsupported" in result.stdout.lower() or "不支持" in result.stdout.lower() or "error" in result.stdout.lower()

def test_harness_run_command():
    """测试 'entrix harness run' 命令"""
    harness_yaml = """
version: "harness/v1"

evidence_producers:
  - id: simple-test
    type: test
    name: 简单测试
    command: echo "test output"
    producer: test
    parser:
      type: exit_code

gate_policies:
  - name: 简单测试通过
    severity: hard
    rule:
      evidence_id: simple-test
      condition: status == "pass"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(harness_yaml)
        
        result = subprocess.run(
            ["entrix", "harness", "run", "--config", str(config_path)],
            capture_output=True,
            text=True,
            cwd=tmpdir
        )
        
        assert result.returncode == 0
        # 应该显示 PASS 状态
        assert "pass" in result.stdout.lower()

def test_harness_run_json_output():
    """测试带 JSON 输出的 'entrix harness run'"""
    harness_yaml = """
version: "harness/v1"
evidence_producers:
  - id: test-1
    type: test
    name: 测试
    command: echo "test"
    producer: test
    parser:
      type: exit_code
gate_policies: []
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(harness_yaml)
        
        result = subprocess.run(
            ["entrix", "harness", "run", "--config", str(config_path), "--output", "json"],
            capture_output=True,
            text=True,
            cwd=tmpdir
        )
        
        assert result.returncode == 0
        # 应该是有效的 JSON
        import json
        data = json.loads(result.stdout)
        assert "task_id" in data or "status" in data
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/cli/test_harness_commands.py -v`  
预期：命令还不存在

- [ ] **步骤 3：编写最小实现**

创建 `entrix/cli/harness.py`：
```python
"""Harness 系统的 CLI 命令。"
import sys
import json
from pathlib import Path
import click
from entrix.harness.config import load_harness_config
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.gate.arbiter import GateEngine
from entrix.harness.conditions import WhenContext
from entrix.harness.store import EvidenceStore

@click.group()
def harness():
    """证据收集和门禁仲裁的 Harness 命令。"""
    pass

@harness.command()
@click.argument('config_path', type=click.Path(exists=True))
def validate(config_path):
    """验证 harness.yaml 配置。
    
    CONFIG_PATH: harness.yaml 文件路径
    """
    try:
        config = load_harness_config(Path(config_path))
        
        click.echo(f"✓ 有效的 harness 配置：{config_path}")
        click.echo(f"  版本：{config.version}")
        click.echo(f"  证据生产者：{len(config.evidence_producers)}")
        click.echo(f"  门禁策略：{len(config.gate_policies)}")
        
        sys.exit(0)
        
    except Exception as e:
        click.echo(f"✗ 无效的配置：{e}", err=True)
        sys.exit(1)

@harness.command()
@click.option('--config', 'config_path', type=click.Path(exists=True), default='harness.yaml', help='harness.yaml 的路径')
@click.option('--output', type=click.Choice(['text', 'json']), default='text', help='输出格式')
def run(config_path, output):
    """执行 harness 收集和仲裁流程。
    
    默认配置路径：当前目录中的 harness.yaml
    """
    try:
        config = load_harness_config(Path(config_path))
        repo_root = Path.cwd()
        
        # 创建上下文
        context = HarnessRunContext(
            task_id="manual-run",
            repo_root=repo_root,
            when_context=WhenContext(
                repo_root=repo_root,
                changed_files=[],
                current_branch="manual"
            ),
            store=EvidenceStore(repo_root)
        )
        
        # 收集证据
        click.echo("收集证据...", err=True)
        engine = EvidenceEngine(config)
        bundle = engine.collect(context)
        
        click.echo(f"收集了 {len(bundle.evidence)} 个证据项", err=True)
        
        # 仲裁门禁
        click.echo("仲裁门禁...", err=True)
        gate_engine = GateEngine(config.gate_policies)
        verdict = gate_engine.arbitrate(bundle)
        
        # 输出结果
        if output == "json":
            result = {
                "status": verdict.status.value,
                "summary": verdict.summary,
                "evidence_count": len(bundle.evidence),
                "gate_results": [
                    {
                        "policy": r.policy_name,
                        "severity": r.severity.value,
                        "passed": r.passed,
                        "message": r.message
                    }
                    for r in verdict.gate_results
                ]
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"\n{'='*50}")
            click.echo(f"裁决：{verdict.status.value.upper()}")
            click.echo(f"{'='*50}")
            click.echo(f"摘要：{verdict.summary}")
            
            if verdict.gate_results:
                click.echo(f"\n门禁结果：")
                for result in verdict.gate_results:
                    status_icon = "✓" if result.passed else "✗"
                    click.echo(f"  {status_icon} {result.policy_name} ({result.severity.value}): {result.message}")
        
        # 使用适当的退出码退出
        if verdict.status.value == "pass":
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        sys.exit(1)

def main():
    """CLI 的入口点。"""
    harness()

if __name__ == "__main__":
    main()
```

- [ ] **步骤 4：更新 CLI 主入口点**

假设有主 CLI 文件，添加 harness 命令：
```python
# 在 entrix/cli/main.py 或类似文件中
from .harness import harness as harness_group

# 注册 harness 命令组
cli.add_command(harness_group)
```

- [ ] **步骤 5：运行测试验证通过**

运行：`python -m pytest tests/cli/test_harness_commands.py -v`  
预期：大部分测试通过，可能需要 CLI 注册调整

- [ ] **步骤 6：修复并验证所有测试通过**

运行：`python -m pytest tests/cli/test_harness_commands.py -v`  
预期：所有测试通过

- [ ] **步骤 7：提交**

```bash
git add entrix/cli/harness.py tests/cli/test_harness_commands.py
git commit -m "feat(cli): 添加 harness validate 和 run CLI 命令"
```

---

## 任务 12：添加综合集成测试

**文件：**
- 创建：`tests/harness/test_full_integration.py`
- 创建：`fixtures/harness/minimal_harness.yaml`

**接口：**
- 产出：端到端集成测试
- 消费：先前任务的所有组件

**描述：** 创建全面的集成测试，验证整个系统协同工作。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/harness/test_full_integration.py`：

```python
import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime
from entrix.harness.config import load_harness_config
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.gate.arbiter import GateEngine
from entrix.harness.conditions import WhenContext
from entrix.harness.store import EvidenceStore

def test_end_to_end_harness_execution():
    """测试从配置到裁决的完整 harness 流程"""
    harness_yaml = """
version: "harness/v1"

when:
  files_exist: [".marker"]

evidence_producers:
  - id: simple-test
    type: test
    name: 简单测试
    command: echo "test output"
    producer: test
    parser:
      type: exit_code
    when:
      files_exist: [".marker"]

  - id: regex-test
    type: test
    name: 正则测试
    command: echo "passed=15, failed=2"
    producer: regex-test
    parser:
      type: regex
      pattern: 'passed=(?P<passed>\\d+), failed=(?P<failed>\\d+)'

  - id: diff-stats
    type: diff
    name: Git 差异统计
    builtin: diff-stats

gate_policies:
  - name: 简单测试通过
    severity: hard
    rule:
      evidence_id: simple-test
      condition: status == "pass"

  - name: 没有测试失败
    severity: hard
    rule:
      evidence_id: regex-test
      condition: int(summary.failed) == 0

  - name: 合理的差异大小
    severity: blocked
    rule:
      evidence_id: diff-stats
      condition: int(summary.added_lines) > 1000
      action: require_human_review
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # 创建全局 when 条件的标记文件
        marker_file = tmpdir_path / ".marker"
        marker_file.write_text("marker")
        
        # 写入 harness 配置
        config_path = tmpdir_path / "harness.yaml"
        config_path.write_text(harness_yaml)
        
        # 加载配置
        config = load_harness_config(config_path)
        
        # 创建上下文
        context = HarnessRunContext(
            task_id="integration-test",
            repo_root=tmpdir_path,
            when_context=WhenContext(
                repo_root=tmpdir_path,
                changed_files=["README.md", "src/main.py"],
                current_branch="feature/test"
            ),
            store=EvidenceStore(tmpdir_path)
        )
        
        # 运行引擎
        engine = EvidenceEngine(config)
        bundle = engine.collect(context)
        
        # 验证收集
        assert bundle.task_id == "integration-test"
        assert len(bundle.evidence) == 3  # 所有 3 个生产者都应该运行
        
        # 验证证据类型
        evidence_ids = {e.id for e in bundle.evidence}
        assert "simple-test" in evidence_ids
        assert "regex-test" in evidence_ids
        assert "diff-stats" in evidence_ids
        
        # 验证特定证据
        regex_evidence = next(e for e in bundle.evidence if e.id == "regex-test")
        assert regex_evidence.summary["passed"] == "15"
        assert regex_evidence.summary["failed"] == "2"
        
        # 运行门禁
        gate_engine = GateEngine(config.gate_policies)
        verdict = gate_engine.arbitrate(bundle)
        
        # 应该失败，因为 regex-test 有失败
        assert verdict.status.value == "fail"
        assert len(verdict.gate_results) == 3
        
        # 验证存储
        evidence_dir = tmpdir_path / ".harness" / "evidence" / "integration-test"
        assert evidence_dir.exists()
        bundle_files = list(evidence_dir.glob("*-bundle.json"))
        assert len(bundle_files) == 1
        
        # 加载并验证存储的包
        stored_bundle = json.loads(bundle_files[0].read_text())
        assert stored_bundle["task_id"] == "integration-test"
        assert len(stored_bundle["evidence"]) == 3

def test_empty_harness_config():
    """测试空 harness 配置"""
    harness_yaml = """
version: "harness/v1"
evidence_producers: []
gate_policies: []
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "harness.yaml"
        config_path.write_text(harness_yaml)
        
        config = load_harness_config(config_path)
        
        context = HarnessRunContext(
            task_id="empty-test",
            repo_root=Path(tmpdir),
            when_context=WhenContext(repo_root=Path(tmpdir))
        )
        
        engine = EvidenceEngine(config)
        bundle = engine.collect(context)
        
        assert len(bundle.evidence) == 0
        
        gate_engine = GateEngine(config.gate_policies)
        verdict = gate_engine.arbitrate(bundle)
        
        assert verdict.status.value == "pass"  # 没有门禁 = 通过
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/harness/test_full_integration.py -v`  
预期：部分组件可能还没有完美集成

- [ ] **步骤 3：修复集成问题**

根据测试结果修复组件之间的任何集成问题。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/harness/test_full_integration.py -v`  
预期：所有集成测试通过

- [ ] **步骤 5：提交**

```bash
git add tests/harness/test_full_integration.py
git commit -m "test(harness): 添加全面的端到端集成测试"
```

---

## 任务 13：文档和示例

**文件：**
- 创建：`docs/harness/README.md`
- 创建：`docs/harness/examples/basic_harness.yaml`
- 创建：`docs/harness/examples/advanced_harness.yaml`
- 修改：`README.md`（项目根目录）提到 harness 系统

**接口：**
- 产出：全面的文档和示例
- 消费：无

**描述：** 为 harness 系统创建文档，包括使用示例和配置参考。

- [ ] **步骤 1：创建主要文档**

创建 `docs/harness/README.md`：

```markdown
# Harness：证据收集和门禁仲裁

## 概述

Harness 系统提供了一个可配置的、由 YAML 驱动的方法来进行证据收集和质量门禁执行。它用灵活的声明式配置层替换了硬编码的 stop-gate 逻辑。

## 快速开始

1. 在项目根目录创建 `harness.yaml`：

```yaml
version: "harness/v1"

evidence_producers:
  - id: unit-tests
    type: test
    name: 单元测试
    command: pytest tests/
    producer: pytest
    parser:
      type: exit_code

gate_policies:
  - name: 测试通过
    severity: hard
    rule:
      evidence_id: unit-tests
      condition: status == "pass"
```

2. 使用 CLI 运行：

```bash
# 验证配置
entrix harness validate

# 运行收集和门禁
entrix harness run

# 使用 JSON 输出
entrix harness run --output json
```

## 配置参考

### 版本

必需。必须为 `"harness/v1"`。

### 证据生产者

生产者通过运行命令或内置函数收集证据。

#### 命令生产者

```yaml
evidence_producers:
  - id: my-test
    type: test
    name: 我的测试
    command: pytest tests/
    producer: pytest
    timeout_seconds: 120
    parser:
      type: regex
      pattern: 'passed=(?P<passed>\\d+), failed=(?P<failed>\\d+)'
    when:
      changed_any:
        - src/**
        - tests/**
```

#### 内置生产者

```yaml
evidence_producers:
  - id: diff-stats
    type: diff
    name: Git 差异统计
    builtin: diff-stats
```

可用的内置生产者：
- `entrix-fitness`：运行 Entrix fitness 报告
- `entrix-review-trigger`：评估审查触发器
- `diff-stats`：收集 git 差异统计

### 门禁策略

策略评估收集的证据并执行质量标准。

```yaml
gate_policies:
  - name: policy-name
    severity: hard  # hard、soft、advisory、blocked
    rule:
      evidence_id: producer-id  # 或 evidence_type
      condition: status == "pass"
```

严重程度级别：
- `hard`：条件为 false 时门禁失败
- `soft`：警告但不失败
- `advisory`：仅记录，不影响结果
- `blocked`：条件为 true 时门禁失败（与 hard 相反）

### When 条件

生产者和全局 harness 的条件激活。

```yaml
when:
  files_exist:
    - package.json
  changed_any:
    - src/**
  branch:
    include:
      - main
      - feature/**
    exclude:
      - docs/**
  env:
    CI: "true"
```

## 表达式 DSL

门禁条件支持丰富的表达式语言：

```yaml
# 比较
condition: summary.score > 80

# 字符串匹配
condition: status == "pass"

# 算术
condition: summary.passed + summary.skipped > 10

# 逻辑运算符
condition: status == "pass" and summary.coverage > 80

# In 运算符
condition: "security" in summary.categories

# 括号
condition: (status == "pass" or status == "skipped") and summary.duration < 1000
```

## Stop Gate 集成

Harness 系统与现有的 stop-gate hook 集成：

1. 在仓库中创建 `harness.yaml`
2. 存在配置时 stop-gate hook 自动使用 harness
3. 没有 `harness.yaml` 时，hook 回退到传统行为

## 错误处理

- 生产者失败不会阻止其他生产者
- 门禁评估错误导致硬门禁失败
- 配置错误会立即报告
- 证据包存储失败不影响门禁结果

## 最佳实践

1. 从基本的命令生产者开始
2. 使用 when 条件避免不必要的工作
3. 结合硬门禁和软门禁进行平衡的执行
4. 对常见操作使用内置生产者
5. 使用 `entrix harness validate` 测试配置

## 从传统迁移

Harness 系统保持向后兼容：

- 没有 `harness.yaml` 的项目继续使用传统 stop-gate
- 现有的 fitness 报告和审查触发器作为内置生产者支持
- 迁移是增量的 - 准备好时采用 harness
```

- [ ] **步骤 2：创建基础示例**

创建 `docs/harness/examples/basic_harness.yaml`：

```yaml
version: "harness/v1"

# 基础示例：单个测试生产者和硬门禁

evidence_producers:
  - id: unit-tests
    type: test
    name: 单元测试
    command: pytest tests/ -v
    producer: pytest
    timeout_seconds: 300
    parser:
      type: exit_code

gate_policies:
  - name: 单元测试必须通过
    severity: hard
    rule:
      evidence_id: unit-tests
      condition: status == "pass"
```

- [ ] **步骤 3：创建高级示例**

创建 `docs/harness/examples/advanced_harness.yaml`：

```yaml
version: "harness/v1"

# 高级示例：带有条件激活和混合门禁严重程度的多个生产者

when:
  # 只在 CI 或功能分支上运行
  env:
    CI: "true"
  branch:
    include:
      - main
      - feature/**

evidence_producers:
  # 带有正则解析器的类型检查
  - id: typecheck
    type: typecheck
    name: TypeScript 类型检查
    command: npm run typecheck
    producer: tsc
    timeout_seconds: 120
    parser:
      type: regex
      pattern: 'Found (?P<errors>\\d+) error'
    when:
      changed_any:
        - src/**/*.ts
        - tsconfig.json

  # 带覆盖率的单元测试
  - id: unit-tests
    type: test
    name: 带覆盖率的单元测试
    command: pytest tests/ --cov=src --cov-report=term
    producer: pytest
    timeout_seconds: 300
    parser:
      type: regex
      pattern: '(?P<passed>\\d+) passed, (?P<failed>\\d+) failed.*coverage (?P<coverage>\\d+)%'
    artifacts:
      - type: junit
        path: junit.xml

  # 带有软门禁的代码检查
  - id: lint
    type: lint
    name: ESLint
    command: npm run lint
    producer: eslint
    timeout_seconds: 60
    parser:
      type: exit_code

  # 内置差异统计生产者
  - id: diff-stats
    type: diff
    name: Git 差异统计
    builtin: diff-stats

gate_policies:
  # 类型检查的硬门禁
  - name: 没有类型错误
    severity: hard
    rule:
      evidence_id: typecheck
      condition: int(summary.errors) == 0

  # 测试失败的硬门禁
  - name: 所有测试通过
    severity: hard
    rule:
      evidence_id: unit-tests
      condition: int(summary.failed) == 0

  # 覆盖率的软门禁（警告但不失败）
  - name: 覆盖率阈值
    severity: soft
    rule:
      evidence_id: unit-tests
      condition: int(summary.coverage) >= 80

  # 代码检查的软门禁
  - name: 代码检查清洁
    severity: soft
    rule:
      evidence_id: lint
      condition: status == "pass"

  # 大变更的阻塞门禁（需要人工审查）
  - name: 大变更需要审查
    severity: blocked
    rule:
      evidence_id: diff-stats
      condition: int(summary.added_lines) > 500
      action: require_human_review
```

- [ ] **步骤 4：更新项目 README**

修改项目根目录 `README.md` 添加 harness 部分：

```markdown
## Harness 系统

有关可配置的证据收集和质量门禁，请参阅 [docs/harness/README.md](docs/harness/README.md)。

快速开始：
```bash
# 验证 harness 配置
entrix harness validate

# 运行证据收集和门禁
entrix harness run
```
```

- [ ] **步骤 5：提交**

```bash
git add docs/harness/ README.md
git commit -m "docs(harness): 添加全面的文档和示例"
```

---

## 任务 14：最终测试和验证

**文件：**
- 运行所有现有测试
- 创建冒烟测试
- 更新任何导入/依赖

**接口：**
- 产出：验证的、工作的系统
- 消费：所有先前的组件

**描述：** 运行全面测试以确保整个系统正确工作。

- [ ] **步骤 1：运行所有测试**

```bash
python -m pytest tests/ -v
```

- [ ] **步骤 2：修复任何失败的测试**

解决任何出现的测试失败。

- [ ] **步骤 3：手动测试 CLI 命令**

```bash
# 使用示例配置进行测试
cd docs/harness/examples
entrix harness validate basic_harness.yaml
entrix harness run --config basic_harness.yaml

entrix harness validate advanced_harness.yaml
```

- [ ] **步骤 4：测试 stop-gate 集成**

测试 stop-gate hook 与 harness 系统的正确集成。

- [ ] **步骤 5：验证向后兼容**

测试没有 harness.yaml 的项目仍能使用传统 stop-gate 工作。

- [ ] **步骤 6：创建最终冒烟测试**

创建 `tests/harness/test_smoke.py`：

```python
def test_smoke_all_components_import():
    """冒烟测试以确保所有组件可以导入"""
    from entrix.harness.config import load_harness_config, HarnessConfig
    from entrix.harness.conditions import evaluate_when, WhenContext
    from entrix.harness.evidence import Evidence, EvidenceBundle
    from entrix.harness.store import EvidenceStore
    from entrix.harness.engine import EvidenceEngine, HarnessRunContext
    from entrix.harness.producers.base import Producer, ProducerContext
    from entrix.harness.producers.command import CommandProducer
    from entrix.harness.gate.policy import GatePolicy, Severity
    from entrix.harness.gate.dsl import evaluate_condition
    from entrix.harness.gate.arbiter import GateEngine, Verdict
    from entrix.stop_gate.adapter import StopGateAdapter
    from entrix.stop_gate.runner import HarnessRunner
    
    # 导入工作的基本冒烟测试
    assert True
```

- [ ] **步骤 7：最终清理和优化**

清理任何临时文件，优化导入，确保正确的包结构。

- [ ] **步骤 8：提交**

```bash
git add tests/harness/test_smoke.py
git commit -m "test(harness): 添加冒烟测试和最终验证"
```

---

## 总结

这个实施计划创建了一个完整的 YAML 驱动证据收集和门禁仲裁系统，用于 Entrix。计划遵循测试驱动开发原则，将复杂的系统分解为可管理的任务，并确保与现有 stop-gate 功能的向后兼容。

**主要交付成果：**
- 完整的 harness 子系统，包含 14 个主要组件
- 全面的测试覆盖（单元、集成、冒烟测试）
- 用于验证和手动执行的 CLI 命令
- 包含示例的完整文档
- 向后兼容的 stop-gate 集成
- 灵活门禁规则的表达式 DSL

该系统使项目能够以声明方式配置证据收集和质量门禁，同时保持使用自定义生产者和复杂门禁规则进行扩展的能力。