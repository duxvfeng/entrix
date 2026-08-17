"""
多智能体协作系统 - 编排智能体实现
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import logging

from multi_agent_base_agents import BaseAgent
from multi_agent_message_bus import (
    Message, MessageBus, MessageType, Priority, metrics
)

logger = logging.getLogger(__name__)


class WorkflowState(Enum):
    """工作流状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """工作流步骤"""
    step_id: str
    agent_id: str
    message_type: MessageType
    payload: Dict[str, Any]
    depends_on: List[str] = None  # 依赖的步骤ID
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class WorkflowResult:
    """工作流结果"""
    workflow_id: str
    state: WorkflowState
    results: Dict[str, Any]
    errors: List[str]
    start_time: str
    end_time: Optional[str] = None


class OrchestratorAgent(BaseAgent):
    """编排智能体 - 协调其他智能体的工作流程"""
    
    def __init__(self, message_bus: MessageBus, project_root: Path):
        super().__init__("orchestrator_agent", message_bus)
        self.project_root = project_root
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        self.workflow_templates = self._initialize_workflow_templates()
        
    def get_capabilities(self) -> List[str]:
        return [
            "workflow_orchestration",
            "task_distribution",
            "result_aggregation",
            "decision_making"
        ]
    
    def _initialize_workflow_templates(self) -> Dict[str, List[WorkflowStep]]:
        """初始化工作流模板"""
        return {
            "code_change_workflow": [
                WorkflowStep(
                    step_id="quality_check",
                    agent_id="quality_gate_agent",
                    message_type=MessageType.QUALITY_CHECK_REQUEST,
                    payload={"tier": "fast"},
                    timeout=60.0
                ),
                WorkflowStep(
                    step_id="deep_review",
                    agent_id="review_agent",
                    message_type=MessageType.REVIEW_REQUEST,
                    payload={"base": "HEAD~1"},
                    depends_on=["quality_check"],
                    timeout=120.0
                ),
                WorkflowStep(
                    step_id="test_analysis",
                    agent_id="test_agent",
                    message_type=MessageType.TEST_ANALYSIS_REQUEST,
                    payload={"base": "HEAD~1"},
                    depends_on=["quality_check"],
                    timeout=90.0
                ),
                WorkflowStep(
                    step_id="documentation_update",
                    agent_id="documentation_agent",
                    message_type=MessageType.DOCUMENTATION_UPDATE_REQUEST,
                    payload={},
                    depends_on=["deep_review", "test_analysis"],
                    timeout=60.0
                )
            ],
            "quality_monitoring_workflow": [
                WorkflowStep(
                    step_id="full_quality_check",
                    agent_id="quality_gate_agent",
                    message_type=MessageType.QUALITY_CHECK_REQUEST,
                    payload={"tier": "normal"},
                    timeout=180.0
                ),
                WorkflowStep(
                    step_id="trend_analysis",
                    agent_id="review_agent",
                    message_type=MessageType.REVIEW_REQUEST,
                    payload={"analysis_type": "trend"},
                    depends_on=["full_quality_check"],
                    timeout=120.0
                )
            ]
        }
    
    async def process_message(self, message: Message) -> Message:
        """处理编排请求"""
        try:
            workflow_type = message.payload.get("workflow_type", "code_change_workflow")
            changed_files = message.payload.get("changed_files", [])
            
            logger.info(f"{self.agent_id} 开始工作流: {workflow_type}")
            
            # 执行工作流
            result = await self.execute_workflow(
                workflow_type, 
                changed_files,
                message.payload
            )
            
            return Message(
                from_agent=self.agent_id,
                payload={
                    "status": "success",
                    "workflow_type": workflow_type,
                    "result": result
                }
            )
            
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            return Message(
                from_agent=self.agent_id,
                payload={
                    "status": "error",
                    "error": str(e)
                }
            )
    
    async def execute_workflow(
        self, 
        workflow_type: str, 
        changed_files: List[str],
        context: Dict[str, Any]
    ) -> WorkflowResult:
        """执行工作流"""
        workflow_id = f"workflow_{asyncio.get_event_loop().time()}"
        start_time = asyncio.get_event_loop().time()
        
        logger.info(f"启动工作流: {workflow_id} - {workflow_type}")
        
        # 获取工作流模板
        if workflow_type not in self.workflow_templates:
            raise ValueError(f"未知工作流类型: {workflow_type}")
        
        steps = self.workflow_templates[workflow_type]
        
        # 初始化工作流状态
        workflow_state = {
            "workflow_id": workflow_id,
            "state": WorkflowState.RUNNING,
            "results": {},
            "errors": [],
            "start_time": start_time,
            "completed_steps": set(),
            "pending_steps": {step.step_id: step for step in steps}
        }
        
        self.active_workflows[workflow_id] = workflow_state
        
        try:
            # 执行所有步骤
            while workflow_state["pending_steps"]:
                # 找到可以执行的步骤（依赖已满足）
                ready_steps = self._get_ready_steps(workflow_state)
                
                if not ready_steps:
                    # 检查是否有循环依赖
                    if workflow_state["pending_steps"]:
                        raise Exception("检测到循环依赖或无法满足的依赖")
                    break
                
                # 并行执行准备好的步骤
                await self._execute_parallel_steps(
                    workflow_state, 
                    ready_steps,
                    changed_files,
                    context
                )
            
            # 工作流完成
            workflow_state["state"] = WorkflowState.COMPLETED
            workflow_state["end_time"] = asyncio.get_event_loop().time()
            
            # 生成结果
            result = WorkflowResult(
                workflow_id=workflow_id,
                state=workflow_state["state"],
                results=workflow_state["results"],
                errors=workflow_state["errors"],
                start_time=str(workflow_state["start_time"]),
                end_time=str(workflow_state["end_time"])
            )
            
            logger.info(f"工作流完成: {workflow_id}")
            return result
            
        except Exception as e:
            logger.error(f"工作流失败: {workflow_id}, 错误: {e}")
            workflow_state["state"] = WorkflowState.FAILED
            workflow_state["errors"].append(str(e))
            
            return WorkflowResult(
                workflow_id=workflow_id,
                state=workflow_state["state"],
                results=workflow_state["results"],
                errors=workflow_state["errors"],
                start_time=str(workflow_state["start_time"])
            )
        finally:
            # 清理工作流状态
            if workflow_id in self.active_workflows:
                del self.active_workflows[workflow_id]
    
    def _get_ready_steps(self, workflow_state: Dict[str, Any]) -> List[WorkflowStep]:
        """获取可以执行的步骤"""
        ready_steps = []
        completed = workflow_state["completed_steps"]
        
        for step_id, step in workflow_state["pending_steps"].items():
            # 检查依赖是否完成
            if step.depends_on:
                if all(dep in completed for dep in step.depends_on):
                    ready_steps.append(step)
            else:
                ready_steps.append(step)
        
        return ready_steps
    
    async def _execute_parallel_steps(
        self, 
        workflow_state: Dict[str, Any],
        steps: List[WorkflowStep],
        changed_files: List[str],
        context: Dict[str, Any]
    ) -> None:
        """并行执行步骤"""
        tasks = []
        
        for step in steps:
            task = self._execute_step(workflow_state, step, changed_files, context)
            tasks.append(task)
        
        # 并行执行所有步骤
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for i, result in enumerate(results):
            step = steps[i]
            if isinstance(result, Exception):
                logger.error(f"步骤 {step.step_id} 失败: {result}")
                workflow_state["errors"].append(str(result))
                
                # 检查是否应该重试
                if step.retry_count < step.max_retries:
                    step.retry_count += 1
                    logger.info(f"重试步骤 {step.step_id} (第 {step.retry_count} 次)")
                    # 将步骤放回待处理队列
                    workflow_state["pending_steps"][step.step_id] = step
                else:
                    # 超过重试次数，标记步骤为失败
                    workflow_state["completed_steps"].add(step.step_id)
                    del workflow_state["pending_steps"][step.step_id]
            else:
                # 步骤成功
                workflow_state["results"][step.step_id] = result
                workflow_state["completed_steps"].add(step.step_id)
                del workflow_state["pending_steps"][step.step_id]
    
    async def _execute_step(
        self, 
        workflow_state: Dict[str, Any],
        step: WorkflowStep,
        changed_files: List[str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行单个步骤"""
        logger.info(f"执行步骤: {step.step_id} -> {step.agent_id}")
        
        # 构建消息
        payload = step.payload.copy()
        payload["changed_files"] = changed_files
        payload["context"] = context
        
        message = Message(
            from_agent=self.agent_id,
            to_agent=step.agent_id,
            message_type=step.message_type,
            payload=payload
        )
        
        try:
            # 发送消息并等待响应
            response = await asyncio.wait_for(
                self.message_bus.request_response(
                    message, 
                    step.agent_id, 
                    timeout=step.timeout
                ),
                timeout=step.timeout
            )
            
            if response.message_type == MessageType.ERROR:
                raise Exception(response.payload.get("error", "未知错误"))
            
            logger.info(f"步骤 {step.step_id} 完成")
            return response.payload
            
        except asyncio.TimeoutError:
            raise Exception(f"步骤 {step.step_id} 超时")
        except Exception as e:
            raise Exception(f"步骤 {step.step_id} 执行失败: {str(e)}")
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """获取工作流状态"""
        if workflow_id in self.active_workflows:
            workflow = self.active_workflows[workflow_id]
            return {
                "workflow_id": workflow_id,
                "state": workflow["state"].value,
                "completed_steps": list(workflow["completed_steps"]),
                "pending_steps": list(workflow["pending_steps"].keys()),
                "results": workflow["results"],
                "errors": workflow["errors"]
            }
        return None
    
    def get_active_workflows(self) -> List[str]:
        """获取活跃工作流列表"""
        return list(self.active_workflows.keys())


class DocumentationAgent(BaseAgent):
    """文档智能体 - 生成和维护技术文档"""
    
    def __init__(self, message_bus: MessageBus, project_root: Path):
        super().__init__("documentation_agent", message_bus)
        self.project_root = project_root
        
    def get_capabilities(self) -> List[str]:
        return [
            "generate_fitness_specs",
            "update_agents_docs",
            "create_architecture_docs"
        ]
    
    async def process_message(self, message: Message) -> Message:
        """处理文档更新请求"""
        try:
            if message.message_type == MessageType.DOCUMENTATION_UPDATE_REQUEST:
                return await self.handle_documentation_update(message)
            else:
                return self.create_error_response("未知消息类型")
        except Exception as e:
            logger.error(f"文档更新失败: {e}")
            return self.create_error_response(str(e))
    
    async def handle_documentation_update(self, message: Message) -> Message:
        """处理文档更新请求"""
        quality_results = message.payload.get("quality_results", {})
        review_results = message.payload.get("review_results", {})
        changed_files = message.payload.get("changed_files", [])
        
        logger.info(f"{self.agent_id} 更新文档")
        
        try:
            # 更新 AGENTS.md
            await self.update_agents_md()
            
            # 生成 fitness 规格文档
            await self.generate_fitness_specs(quality_results)
            
            response = Message(
                from_agent=self.agent_id,
                payload={
                    "status": "success",
                    "updated_files": ["AGENTS.md", "harness.yaml"],
                    "changed_files": changed_files
                }
            )
            
        except Exception as e:
            response = self.create_error_response(str(e))
        
        return response
    
    async def update_agents_md(self) -> None:
        """更新 AGENTS.md 文档"""
        agents_md_path = self.project_root / "AGENTS.md"
        
        content = """# AI 智能体协作指南

## 概述
本项目使用多智能体协作系统进行代码质量保障和自动化审查。

## 智能体角色

### 1. 质量门禁智能体 (quality_gate_agent)
- **职责**: 执行 Entrix 质量检查
- **能力**: 
  - 快速质量检查 (`entrix run --tier fast`)
  - 完整质量检查 (`entrix run --tier normal`)
  - 配置验证 (`entrix validate`)

### 2. 代码审查智能体 (review_agent)
- **职责**: 深度代码审查和影响分析
- **能力**:
  - 审查触发器 (`entrix review-trigger`)
  - 影响分析 (`entrix graph impact`)
  - 审查上下文生成

### 3. 测试智能体 (test_agent)
- **职责**: 测试半径分析和测试执行
- **能力**:
  - 测试半径分析 (`entrix graph test-radius`)
  - 测试覆盖度分析
  - 相关测试识别

### 4. 编排智能体 (orchestrator_agent)
- **职责**: 协调各智能体工作流程
- **能力**:
  - 工作流编排
  - 任务分发
  - 结果聚合
  - 决策制定

### 5. 文档智能体 (documentation_agent)
- **职责**: 生成和维护技术文档
- **能力**:
  - 生成 fitness 规格
  - 更新智能体文档
  - 创建架构文档

## 工作流程

### 代码变更工作流
1. **质量检查** → 快速检查代码质量
2. **深度审查** → 对通过快速检查的变更进行深度审查
3. **测试分析** → 分析变更影响的测试
4. **文档更新** → 更新相关文档

### 质量监控工作流
1. **完整质量检查** → 执行所有质量检查
2. **趋势分析** → 分析质量趋势

## 使用方法

### 通过编排智能体启动工作流
```python
# 发送工作流请求到编排智能体
message = Message(
    from_agent="user",
    to_agent="orchestrator_agent",
    message_type=MessageType.WORKFLOW_REQUEST,
    payload={
        "workflow_type": "code_change_workflow",
        "changed_files": ["src/main.py"]
    }
)
```

### 直接调用特定智能体
```python
# 直接调用质量检查
quality_message = Message(
    from_agent="user",
    to_agent="quality_gate_agent",
    message_type=MessageType.QUALITY_CHECK_REQUEST,
    payload={"tier": "fast"}
)
```

## 智能体通信协议

所有智能体通过消息总线进行异步通信：
- **消息类型**: 请求、响应、通知、错误
- **优先级**: 高、中、低
- **超时处理**: 支持可配置超时和重试
- **错误处理**: 熔断器保护和死信队列

## 监控和可观测性

### 指标收集
- 智能体执行时间
- 成功率和错误率
- 消息队列大小
- 熔断器状态

### 日志记录
- 结构化日志记录所有智能体活动
- 消息追踪和调试支持
- 性能监控

## 故障处理

### 熔断器保护
每个智能体都有熔断器保护，防止单个智能体故障影响整个系统。

### 重试机制
支持指数退避重试策略，最大重试次数可配置。

### 降级处理
在智能体不可用时，系统可以降级到基本功能。

## 扩展性

### 添加新智能体
1. 继承 `BaseAgent` 基类
2. 实现 `process_message` 方法
3. 在消息总线中注册
4. 更新工作流模板

### 自定义工作流
可以在编排智能体中定义新的工作流模板。

## 维护者
- Entrix 质量保障团队
- 多智能体协作系统维护者

"""
        await asyncio.to_thread(
            agents_md_path.write_text, 
            content, 
            encoding='utf-8'
        )
    
    async def generate_fitness_specs(self, quality_results: Dict[str, Any]) -> None:
        """生成单文件 Harness 配置。"""
        base_quality_spec = """version: "harness/v1"
fitness:
  dimensions:
    - dimension: code_quality
      weight: 100
      threshold: {pass: 90, warn: 80}
      metrics:
        - name: lint
          command: npm run lint 2>&1
          hard_gate: true
          tier: fast
          description: 代码检查必须通过
        - name: unit_tests
          command: npm run test:run 2>&1
          pattern: "Tests\\s+\\d+\\s+passed"
          hard_gate: true
          tier: normal
          description: 单元测试必须通过
review_triggers: {rules: []}
evidence_producers: []
gate_policies: []
"""

        quality_spec_path = self.project_root / "harness.yaml"
        await asyncio.to_thread(
            quality_spec_path.write_text,
            base_quality_spec,
            encoding='utf-8'
        )
    
    def create_error_response(self, error_message: str) -> Message:
        """创建错误响应"""
        return Message(
            from_agent=self.agent_id,
            payload={
                "status": "error",
                "error": error_message
            }
        )
