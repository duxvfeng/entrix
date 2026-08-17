"""
多智能体协作系统 - 集成和使用示例
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List
import logging

# 导入所有必需的模块
from multi_agent_message_bus import (
    MessageBus, Message, MessageType, Priority, metrics
)
from multi_agent_base_agents import (
    QualityGateAgent, ReviewAgent, TestAgent
)
from multi_agent_orchestrator import (
    OrchestratorAgent, DocumentationAgent
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiAgentSystem:
    """多智能体系统集成管理器"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.message_bus = MessageBus()
        self.agents = {}
        self._running = False
        
    async def initialize(self) -> None:
        """初始化系统"""
        logger.info("初始化多智能体协作系统")
        
        # 创建智能体实例
        self.agents = {
            "quality_gate_agent": QualityGateAgent(self.message_bus, self.project_root),
            "review_agent": ReviewAgent(self.message_bus, self.project_root),
            "test_agent": TestAgent(self.message_bus, self.project_root),
            "orchestrator_agent": OrchestratorAgent(self.message_bus, self.project_root),
            "documentation_agent": DocumentationAgent(self.message_bus, self.project_root)
        }
        
        # 启动所有智能体
        for agent_id, agent in self.agents.items():
            await agent.start()
            logger.info(f"启动智能体: {agent_id}")
        
        self._running = True
        logger.info("多智能体系统初始化完成")
    
    async def shutdown(self) -> None:
        """关闭系统"""
        logger.info("关闭多智能体协作系统")
        self._running = False
        
        # 停止所有智能体
        for agent_id, agent in self.agents.items():
            await agent.stop()
            logger.info(f"停止智能体: {agent_id}")
    
    async def execute_workflow(
        self, 
        workflow_type: str = "code_change_workflow",
        changed_files: List[str] = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """执行工作流"""
        if not self._running:
            raise RuntimeError("系统未启动")
        
        if changed_files is None:
            changed_files = []
        if context is None:
            context = {}
        
        logger.info(f"执行工作流: {workflow_type}")
        
        # 发送工作流请求到编排智能体
        orchestrator = self.agents["orchestrator_agent"]
        message = Message(
            from_agent="system",
            to_agent="orchestrator_agent",
            message_type=MessageType.AGGREGATION_REQUEST,
            payload={
                "workflow_type": workflow_type,
                "changed_files": changed_files,
                **context
            }
        )
        
        response = await orchestrator.handle_message(message)
        
        return response.payload
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = {
            "system_running": self._running,
            "agents": {},
            "metrics": {}
        }
        
        # 收集各智能体状态
        for agent_id, agent in self.agents.items():
            status["agents"][agent_id] = agent.get_status()
            status["metrics"][agent_id] = metrics.get_metrics(agent_id)
        
        return status
    
    def print_system_status(self) -> None:
        """打印系统状态"""
        status = asyncio.get_event_loop().run_until_complete(self.get_system_status())
        
        print("\n=== 多智能体系统状态 ===")
        print(f"系统运行状态: {status['system_running']}")
        print("\n智能体状态:")
        
        for agent_id, agent_status in status['agents'].items():
            print(f"\n{agent_id}:")
            print(f"  状态: {agent_status['state']}")
            print(f"  能力: {', '.join(agent_status['capabilities'])}")
            print(f"  熔断器状态: {agent_status['circuit_breaker_state']}")
            
            agent_metrics = agent_status.get('metrics', {})
            if agent_metrics:
                print(f"  指标:")
                print(f"    总消息数: {agent_metrics.get('total_messages', 0)}")
                print(f"    成功率: {agent_metrics.get('success_rate', 0):.2%}")
                print(f"    平均执行时间: {agent_metrics.get('avg_execution_time', 0):.2f}s")


async def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")
    
    # 初始化系统
    project_root = Path("/Users/apple/entrix")
    system = MultiAgentSystem(project_root)
    await system.initialize()
    
    try:
        # 执行代码变更工作流
        result = await system.execute_workflow(
            workflow_type="code_change_workflow",
            changed_files=["src/main.py", "tests/test_main.py"]
        )
        
        print("\n工作流执行结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 打印系统状态
        system.print_system_status()
        
    finally:
        await system.shutdown()


async def example_direct_agent_call():
    """直接调用智能体示例"""
    print("\n=== 直接调用智能体示例 ===")
    
    project_root = Path("/Users/apple/entrix")
    system = MultiAgentSystem(project_root)
    await system.initialize()
    
    try:
        # 直接调用质量检查智能体
        quality_agent = system.agents["quality_gate_agent"]
        
        message = Message(
            from_agent="user",
            to_agent="quality_gate_agent",
            message_type=MessageType.QUALITY_CHECK_REQUEST,
            payload={"tier": "fast"}
        )
        
        response = await quality_agent.handle_message(message)
        
        print("\n质量检查结果:")
        print(json.dumps(response.payload, indent=2, ensure_ascii=False))
        
    finally:
        await system.shutdown()


async def example_parallel_workflow():
    """并行工作流示例"""
    print("\n=== 并行工作流示例 ===")
    
    project_root = Path("/Users/apple/entrix")
    system = MultiAgentSystem(project_root)
    await system.initialize()
    
    try:
        # 创建多个并行工作流
        tasks = []
        
        # 模拟多个代码变更
        changed_files_sets = [
            ["src/module_a.py"],
            ["src/module_b.py"],
            ["src/module_c.py"]
        ]
        
        for files in changed_files_sets:
            task = system.execute_workflow(
                workflow_type="code_change_workflow",
                changed_files=files
            )
            tasks.append(task)
        
        # 并行执行所有工作流
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        print("\n并行工作流执行结果:")
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"工作流 {i+1} 失败: {result}")
            else:
                print(f"工作流 {i+1} 完成:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
        
    finally:
        await system.shutdown()


async def example_error_handling():
    """错误处理示例"""
    print("\n=== 错误处理示例 ===")
    
    project_root = Path("/Users/apple/entrix")
    system = MultiAgentSystem(project_root)
    await system.initialize()
    
    try:
        # 模拟错误场景 - 发送无效的消息类型
        orchestrator = system.agents["orchestrator_agent"]
        
        invalid_message = Message(
            from_agent="user",
            to_agent="orchestrator_agent",
            message_type=MessageType.QUALITY_CHECK_REQUEST,  # 错误的消息类型
            payload={"invalid": "data"}
        )
        
        response = await orchestrator.handle_message(invalid_message)
        
        print("\n错误处理结果:")
        print(json.dumps(response.payload, indent=2, ensure_ascii=False))
        
        # 查看系统状态，检查错误处理机制
        system.print_system_status()
        
    finally:
        await system.shutdown()


async def example_monitoring():
    """监控和指标示例"""
    print("\n=== 监控和指标示例 ===")
    
    project_root = Path("/Users/apple/entrix")
    system = MultiAgentSystem(project_root)
    await system.initialize()
    
    try:
        # 执行多个工作流以生成指标数据
        for i in range(3):
            await system.execute_workflow(
                workflow_type="code_change_workflow",
                changed_files=[f"src/file_{i}.py"]
            )
        
        # 获取详细指标
        status = await system.get_system_status()
        
        print("\n详细系统指标:")
        print(json.dumps(status, indent=2, ensure_ascii=False))
        
        # 分析性能趋势
        print("\n性能分析:")
        for agent_id, agent_metrics in status['metrics'].items():
            if agent_metrics:
                print(f"\n{agent_id}:")
                print(f"  成功率: {agent_metrics['success_rate']:.2%}")
                print(f"  平均执行时间: {agent_metrics['avg_execution_time']:.2f}s")
                print(f"  最长执行时间: {agent_metrics['max_execution_time']:.2f}s")
                print(f"  最短执行时间: {agent_metrics['min_execution_time']:.2f}s")
        
    finally:
        await system.shutdown()


class CommandLineInterface:
    """命令行接口"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.system = None
        
    async def start(self):
        """启动系统"""
        self.system = MultiAgentSystem(self.project_root)
        await self.system.initialize()
        print("多智能体协作系统已启动")
        
    async def stop(self):
        """停止系统"""
        if self.system:
            await self.system.shutdown()
            print("多智能体协作系统已停止")
    
    async def run_command(self, command: str, args: List[str] = None) -> Dict[str, Any]:
        """运行命令"""
        if args is None:
            args = []
        
        if command == "workflow":
            # 执行工作流
            workflow_type = args[0] if args else "code_change_workflow"
            return await self.system.execute_workflow(workflow_type=workflow_type)
        
        elif command == "status":
            # 获取系统状态
            return await self.system.get_system_status()
        
        elif command == "check":
            # 快速质量检查
            return await self.system.execute_workflow(
                workflow_type="code_change_workflow",
                changed_files=args
            )
        
        else:
            return {"error": f"未知命令: {command}"}


async def main():
    """主函数 - 演示所有功能"""
    print("🤖 多智能体协作系统演示\n")
    
    # 运行所有示例
    await example_basic_usage()
    await example_direct_agent_call()
    await example_parallel_workflow()
    await example_error_handling()
    await example_monitoring()
    
    print("\n✅ 所有示例执行完成")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(main())
    
    # 或者使用命令行接口
    # python multi_agent_integration.py workflow code_change_workflow
    # python multi_agent_integration.py status
    # python multi_agent_integration.py check src/main.py