# 多智能体协作系统

基于 Entrix 质量保障系统的多智能体协作开发框架。

## 🎯 设计理念

本项目实现了一个灵活的多智能体协作系统，将复杂的代码质量保障任务分解到专门的智能体中，通过标准化的消息总线进行通信，实现高效、可扩展的协作开发模式。

## 🏗️ 系统架构

### 核心组件

```
多智能体协作系统
├── 消息总线 (Message Bus)          # 异步通信基础设施
├── 智能体基类 (Base Agent)         # 统一的智能体接口
├── 专门智能体                      # 各司其职的专业智能体
│   ├── 质量门禁智能体             # Entrix 质量检查
│   ├── 代码审查智能体             # 深度代码审查
│   ├── 测试智能体                 # 测试分析
│   ├── 编排智能体                 # 工作流协调
│   └── 文档智能体                 # 文档生成维护
└── 工作流引擎                     # 任务编排和执行
```

### 消息传递架构

```
用户请求 → 编排智能体 → 消息总线 → 各专门智能体 → 结果聚合 → 响应
```

## 🚀 核心特性

### 1. 关注点分离
- **质量门禁智能体**: 专注于代码质量检查和适应度函数评估
- **代码审查智能体**: 专注于深度代码审查和架构影响分析
- **测试智能体**: 专注于测试半径分析和覆盖度评估
- **编排智能体**: 专注于工作流程协调和决策制定
- **文档智能体**: 专注于技术文档的自动生成和维护

### 2. 弹性设计
- **熔断器保护**: 防止单个智能体故障影响整体系统
- **重试机制**: 指数退避重试策略，提高系统稳定性
- **死信队列**: 专门的失败消息处理机制
- **优雅降级**: 智能体不可用时的降级处理

### 3. 可扩展性
- **插件式架构**: 新智能体可以轻松集成到系统中
- **工作流模板**: 可配置的执行流程，支持自定义
- **水平扩展**: 支持多实例部署和负载均衡

### 4. 可观测性
- **指标收集**: 详细的性能指标和成功率监控
- **结构化日志**: 完整的日志记录和分布式追踪
- **状态监控**: 实时的智能体状态和工作流执行情况

## 📁 文件结构

```
docs/multi_agent_system/
├── README.md                         # 本文件
├── multi_agent_system_guide.md       # 完整的系统指南
├── multi_agent_architecture.py       # 架构设计定义
├── multi_agent_message_bus.py        # 消息总线实现
├── multi_agent_base_agents.py        # 基础智能体框架
├── multi_agent_orchestrator.py       # 编排智能体实现
└── multi_agent_integration.py        # 集成和使用示例
```

## 🛠️ 快速开始

### 1. 基础使用

```python
import asyncio
from pathlib import Path
from docs.multi_agent_system.multi_agent_integration import MultiAgentSystem

async def main():
    # 初始化系统
    project_root = Path("/path/to/your/project")
    system = MultiAgentSystem(project_root)
    await system.initialize()
    
    try:
        # 执行代码变更工作流
        result = await system.execute_workflow(
            workflow_type="code_change_workflow",
            changed_files=["src/main.py"]
        )
        print(result)
    finally:
        await system.shutdown()

asyncio.run(main())
```

### 2. 直接调用智能体

```python
# 直接调用质量检查智能体
quality_agent = system.agents["quality_gate_agent"]

message = Message(
    from_agent="user",
    to_agent="quality_gate_agent", 
    message_type=MessageType.QUALITY_CHECK_REQUEST,
    payload={"tier": "fast"}
)

response = await quality_agent.handle_message(message)
```

### 3. 工作流自定义

```python
# 执行自定义工作流
custom_workflow = {
    "steps": [
        {
            "step_id": "quality_check",
            "agent_id": "quality_gate_agent",
            "payload": {"tier": "normal"}
        },
        {
            "step_id": "documentation",
            "agent_id": "documentation_agent",
            "depends_on": ["quality_check"]
        }
    ]
}
```

## 🎨 协作模式

### 1. 流水线模式
```
输入 → [质量检查] → [代码审查] → [测试分析] → 输出
```
适用于顺序处理的场景，确保每个步骤按顺序执行。

### 2. 并行处理模式
```
输入 → [质量检查] → 并行执行 → [审查] + [测试] → 结果聚合 → 输出
```
适用于独立任务的并行处理，提高整体效率。

### 3. 编排模式
```
[编排智能体] → 任务分发 → [各专门智能体] → 结果聚合 → 决策输出
```
适用于复杂工作流的中央协调管理。

## 📊 智能体能力矩阵

| 智能体 | 核心能力 | Entrix 集成 | 主要输出 |
|--------|----------|-------------|----------|
| 质量门禁智能体 | 快速/完整质量检查 | `entrix run` | 质量评估报告 |
| 代码审查智能体 | 深度审查和影响分析 | `entrix review-trigger`, `entrix graph impact` | 审查建议 |
| 测试智能体 | 测试半径分析 | `entrix graph test-radius` | 测试覆盖报告 |
| 编排智能体 | 工作流编排和决策 | 工作流模板 | 协调结果 |
| 文档智能体 | 文档生成维护 | 自动文档生成 | 更新的文档 |

## 🔧 错误处理策略

### 熔断器保护
```python
# 智能体失败 5 次后熔断器打开
circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60.0)

# 熔断器状态转换
CLOSED → OPEN → HALF_OPEN → CLOSED
```

### 重试机制
```python
# 指数退避重试
retry_policy = {
    "max_retries": 3,
    "base_delay": 1.0,
    "max_delay": 60.0,
    "exponent_base": 2
}
```

### 死信队列处理
```python
# 失败消息进入死信队列
dead_letter_queue = asyncio.Queue()

# 异步处理失败消息
async def process_dead_letter_queue():
    while not dead_letter_queue.empty():
        message = await dead_letter_queue.get()
        # 实现重试或其他处理逻辑
```

## 📈 监控和指标

### 系统指标
```python
# 查看智能体性能指标
agent_metrics = metrics.get_metrics("quality_gate_agent")

# 示例输出
{
    "total_messages": 150,
    "success_rate": 0.95,
    "avg_execution_time": 2.3,
    "error_count": 7
}
```

### 健康检查
```python
# 获取系统状态
system_status = await system.get_system_status()

# 检查特定智能体
agent_status = system.agents["quality_gate_agent"].get_status()
```

## 🔄 工作流模板

### 代码变更工作流
```yaml
steps:
  - id: quality_check
    agent: quality_gate_agent
    action: entrix run --tier fast
    timeout: 60s
    
  - id: deep_review  
    agent: review_agent
    action: entrix review-trigger --base HEAD~1
    depends_on: [quality_check]
    timeout: 120s
    
  - id: test_analysis
    agent: test_agent
    action: entrix graph test-radius --base HEAD~1
    depends_on: [quality_check]
    timeout: 90s
    
  - id: documentation
    agent: documentation_agent
    action: update_docs
    depends_on: [deep_review, test_analysis]
    timeout: 60s
```

### 质量监控工作流
```yaml
steps:
  - id: full_quality_check
    agent: quality_gate_agent
    action: entrix run --tier normal
    timeout: 180s
    
  - id: trend_analysis
    agent: review_agent
    action: analyze_quality_trends
    depends_on: [full_quality_check]
    timeout: 120s
```

## 🚦 部署选项

### 本地开发
```bash
# 直接运行
python docs/multi_agent_system/multi_agent_integration.py
```

### Docker 容器化
```yaml
# docker-compose.yml
services:
  orchestrator:
    build: .
    environment:
      - AGENT_TYPE=orchestrator
      - MESSAGE_BUS_URL=redis://message-bus:6379
    volumes:
      - ./project:/workspace
```

### Kubernetes 部署
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: quality-gate-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: quality-gate-agent
  template:
    metadata:
      labels:
        app: quality-gate-agent
    spec:
      containers:
      - name: agent
        image: entrix-agent:latest
        env:
        - name: AGENT_TYPE
          value: "quality_gate"
```

## 🧪 测试

### 单元测试
```python
# 测试单个智能体
async def test_quality_gate_agent():
    agent = QualityGateAgent(message_bus, project_root)
    await agent.start()
    
    message = Message(
        from_agent="test",
        to_agent="quality_gate_agent",
        message_type=MessageType.QUALITY_CHECK_REQUEST,
        payload={"tier": "fast"}
    )
    
    response = await agent.handle_message(message)
    assert response.payload["status"] == "success"
```

### 集成测试
```python
# 测试完整工作流
async def test_code_change_workflow():
    system = MultiAgentSystem(project_root)
    await system.initialize()
    
    result = await system.execute_workflow(
        workflow_type="code_change_workflow",
        changed_files=["src/test.py"]
    )
    
    assert result["state"] == "completed"
    await system.shutdown()
```

## 🔐 安全考虑

### 消息验证
```python
# 验证消息来源
def validate_message(message: Message) -> bool:
    if message.from_agent not in registered_agents:
        return False
    # 其他验证逻辑
    return True
```

### 权限控制
```python
# 智能体权限管理
agent_permissions = {
    "quality_gate_agent": ["read_code", "run_tests"],
    "review_agent": ["read_code", "analyze_structure"],
    "documentation_agent": ["read_code", "write_docs"]
}
```

## 📚 扩展开发

### 添加新智能体
```python
class CustomAgent(BaseAgent):
    def __init__(self, message_bus: MessageBus, project_root: Path):
        super().__init__("custom_agent", message_bus)
        
    async def process_message(self, message: Message) -> Message:
        # 实现自定义逻辑
        pass
        
    def get_capabilities(self) -> List[str]:
        return ["custom_capability"]
```

### 自定义工作流
```python
# 在编排智能体中添加新模板
workflow_templates["custom_workflow"] = [
    WorkflowStep(
        step_id="custom_step",
        agent_id="custom_agent",
        message_type=MessageType.CUSTOM_REQUEST,
        payload={"custom_param": "value"}
    )
]
```

## 🤝 贡献指南

1. 遵循现有的智能体接口设计
2. 实现完整的错误处理和日志记录
3. 添加相应的测试用例
4. 更新文档和示例
5. 确保与现有系统的兼容性

## 📖 相关文档

- [完整系统指南](multi_agent_system_guide.md) - 详细的架构和实现说明
- [架构设计](multi_agent_architecture.py) - 核心架构定义
- [消息总线](multi_agent_message_bus.py) - 通信机制实现
- [基础智能体](multi_agent_base_agents.py) - 智能体框架
- [编排系统](multi_agent_orchestrator.py) - 工作流编排
- [集成示例](multi_agent_integration.py) - 使用示例和最佳实践

## 🎯 最佳实践

1. **消息设计**: 保持消息格式简单一致，包含必要上下文
2. **错误处理**: 优雅降级，提供详细错误信息，适当重试
3. **性能优化**: 避免长时间同步操作，使用异步处理
4. **监控告警**: 建立完善的监控体系，及时发现问题
5. **文档维护**: 保持文档与代码同步更新

## ⚡ 性能优化建议

1. **并发处理**: 利用异步处理提高吞吐量
2. **缓存策略**: 缓存常用数据和结果
3. **连接复用**: 使用连接池减少资源开销
4. **批量处理**: 支持批量消息处理
5. **资源限制**: 设置合理的队列大小和超时

这个多智能体协作系统为现代软件开发提供了一个强大、灵活的自动化质量保障框架，通过明确的角色分工和标准化的协作模式，实现了高效的软件开发和质量保障流程。