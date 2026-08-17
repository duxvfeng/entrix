"""
多智能体协作系统 - 基础智能体框架
"""

import asyncio
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import logging

from multi_agent_message_bus import (
    Message, MessageBus, MessageType, Priority, 
    message_bus, metrics, CircuitBreaker
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """智能体基类"""
    
    def __init__(self, agent_id: str, message_bus: MessageBus):
        self.agent_id = agent_id
        self.message_bus = message_bus
        self.circuit_breaker = CircuitBreaker()
        self.state = "idle"
        self.capabilities: List[str] = []
        self._running = False
        
    @abstractmethod
    async def process_message(self, message: Message) -> Message:
        """处理消息的抽象方法"""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """获取智能体能力"""
        pass
    
    async def start(self) -> None:
        """启动智能体"""
        self._running = True
        self.message_bus.register_agent(self.agent_id, self.handle_message)
        logger.info(f"{self.agent_id} 启动")
        
        # 启动消息处理循环
        asyncio.create_task(self.message_loop())
    
    async def stop(self) -> None:
        """停止智能体"""
        self._running = False
        logger.info(f"{self.agent_id} 停止")
    
    async def message_loop(self) -> None:
        """消息处理循环"""
        while self._running:
            try:
                message = await self.message_bus.subscribe_to_messages(self.agent_id)
                
                # 使用熔断器处理消息
                start_time = asyncio.get_event_loop().time()
                try:
                    response = await self.circuit_breaker.call(
                        self.process_message, message
                    )
                    duration = asyncio.get_event_loop().time() - start_time
                    
                    # 记录指标
                    metrics.record_execution(self.agent_id, duration, True)
                    
                    # 发送响应
                    if message.reply_to:
                        response.to_agent = message.reply_to
                        response.from_agent = self.agent_id
                        response.message_type = MessageType.RESPONSE
                        response.correlation_id = message.id
                        await self.message_bus.publish(response)
                        
                except Exception as e:
                    duration = asyncio.get_event_loop().time() - start_time
                    metrics.record_execution(self.agent_id, duration, False)
                    logger.error(f"{self.agent_id} 处理消息失败: {e}")
                    
                    # 发送错误响应
                    if message.reply_to:
                        error_response = Message(
                            from_agent=self.agent_id,
                            to_agent=message.reply_to,
                            message_type=MessageType.ERROR,
                            payload={"error": str(e), "original_message": message.to_dict()},
                            correlation_id=message.id
                        )
                        await self.message_bus.publish(error_response)
                    
            except Exception as e:
                logger.error(f"{self.agent_id} 消息循环错误: {e}")
                await asyncio.sleep(1)
    
    async def send_message(self, to_agent: str, message_type: MessageType, 
                          payload: Dict[str, Any], priority: Priority = Priority.MEDIUM) -> Message:
        """发送消息到其他智能体"""
        message = Message(
            from_agent=self.agent_id,
            to_agent=to_agent,
            message_type=message_type,
            payload=payload,
            priority=priority
        )
        await self.message_bus.publish(message)
        return message
    
    async def request_response(self, to_agent: str, message_type: MessageType,
                              payload: Dict[str, Any], timeout: float = 30.0) -> Message:
        """发送请求并等待响应"""
        message = Message(
            from_agent=self.agent_id,
            to_agent=to_agent,
            message_type=message_type,
            payload=payload
        )
        return await self.message_bus.request_response(message, timeout)
    
    async def handle_message(self, message: Message) -> Message:
        """外部消息处理接口"""
        return await self.process_message(message)
    
    def get_status(self) -> Dict[str, Any]:
        """获取智能体状态"""
        agent_metrics = metrics.get_metrics(self.agent_id)
        return {
            "agent_id": self.agent_id,
            "state": self.state,
            "capabilities": self.capabilities,
            "circuit_breaker_state": self.circuit_breaker.state,
            "metrics": agent_metrics
        }


class QualityGateAgent(BaseAgent):
    """质量门禁智能体"""
    
    def __init__(self, message_bus: MessageBus, project_root: Path):
        super().__init__("quality_gate_agent", message_bus)
        self.project_root = project_root
        
    def get_capabilities(self) -> List[str]:
        return [
            "entrix_run_fast",
            "entrix_run_normal", 
            "entrix_validate",
            "quality_assessment"
        ]
    
    async def process_message(self, message: Message) -> Message:
        """处理质量检查请求"""
        try:
            if message.message_type == MessageType.QUALITY_CHECK_REQUEST:
                return await self.handle_quality_check(message)
            else:
                return self.create_error_response("未知消息类型")
        except Exception as e:
            logger.error(f"质量检查失败: {e}")
            return self.create_error_response(str(e))
    
    async def handle_quality_check(self, message: Message) -> Message:
        """处理质量检查"""
        tier = message.payload.get("tier", "fast")
        changed_files = message.payload.get("changed_files", [])
        
        logger.info(f"{self.agent_id} 执行质量检查: tier={tier}")
        
        # 执行 Entrix 检查
        try:
            if tier == "fast":
                result = await self.run_entrix_command(
                    ["entrix", "run", "--tier", "fast", "--json"]
                )
            elif tier == "normal":
                result = await self.run_entrix_command(
                    ["entrix", "run", "--tier", "normal", "--json"]
                )
            else:
                result = await self.run_entrix_command(
                    ["entrix", "validate", "--json"]
                )
            
            response = Message(
                from_agent=self.agent_id,
                payload={
                    "status": "success",
                    "tier": tier,
                    "result": result,
                    "changed_files": changed_files
                }
            )
            
        except subprocess.CalledProcessError as e:
            response = Message(
                from_agent=self.agent_id,
                payload={
                    "status": "failed",
                    "error": str(e),
                    "exit_code": e.returncode
                }
            )
        except Exception as e:
            response = self.create_error_response(str(e))
        
        return response
    
    async def run_entrix_command(self, command: List[str]) -> Dict[str, Any]:
        """运行 Entrix 命令"""
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, command, stdout, stderr
                )
            
            # 解析 JSON 输出
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                result = {"raw_output": stdout}
            
            return result
            
        except Exception as e:
            logger.error(f"执行命令失败: {' '.join(command)}, 错误: {e}")
            raise
    
    def create_error_response(self, error_message: str) -> Message:
        """创建错误响应"""
        return Message(
            from_agent=self.agent_id,
            payload={
                "status": "error",
                "error": error_message
            }
        )


class ReviewAgent(BaseAgent):
    """代码审查智能体"""
    
    def __init__(self, message_bus: MessageBus, project_root: Path):
        super().__init__("review_agent", message_bus)
        self.project_root = project_root
        
    def get_capabilities(self) -> List[str]:
        return [
            "review_trigger",
            "graph_impact_analysis",
            "code_review"
        ]
    
    async def process_message(self, message: Message) -> Message:
        """处理审查请求"""
        try:
            if message.message_type == MessageType.REVIEW_REQUEST:
                return await self.handle_review_request(message)
            else:
                return self.create_error_response("未知消息类型")
        except Exception as e:
            logger.error(f"审查失败: {e}")
            return self.create_error_response(str(e))
    
    async def handle_review_request(self, message: Message) -> Message:
        """处理审查请求"""
        base = message.payload.get("base", "HEAD~1")
        changed_files = message.payload.get("changed_files", [])
        
        logger.info(f"{self.agent_id} 执行代码审查: base={base}")
        
        try:
            # 运行 review-trigger
            review_result = await self.run_entrix_command(
                ["entrix", "review-trigger", "--base", base, "--json"]
            )
            
            # 运行影响分析
            impact_result = await self.run_entrix_command(
                ["entrix", "graph", "impact", "--base", base, "--json"]
            )
            
            response = Message(
                from_agent=self.agent_id,
                payload={
                    "status": "success",
                    "review": review_result,
                    "impact": impact_result,
                    "changed_files": changed_files
                }
            )
            
        except Exception as e:
            response = self.create_error_response(str(e))
        
        return response
    
    async def run_entrix_command(self, command: List[str]) -> Dict[str, Any]:
        """运行 Entrix 命令"""
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, command, stdout, stderr
                )
            
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                result = {"raw_output": stdout}
            
            return result
            
        except Exception as e:
            logger.error(f"执行命令失败: {' '.join(command)}, 错误: {e}")
            raise
    
    def create_error_response(self, error_message: str) -> Message:
        """创建错误响应"""
        return Message(
            from_agent=self.agent_id,
            payload={
                "status": "error",
                "error": error_message
            }
        )


class TestAgent(BaseAgent):
    """测试智能体"""
    
    def __init__(self, message_bus: MessageBus, project_root: Path):
        super().__init__("test_agent", message_bus)
        self.project_root = project_root
        
    def get_capabilities(self) -> List[str]:
        return [
            "test_radius_analysis",
            "test_execution",
            "coverage_analysis"
        ]
    
    async def process_message(self, message: Message) -> Message:
        """处理测试请求"""
        try:
            if message.message_type == MessageType.TEST_ANALYSIS_REQUEST:
                return await self.handle_test_analysis(message)
            else:
                return self.create_error_response("未知消息类型")
        except Exception as e:
            logger.error(f"测试分析失败: {e}")
            return self.create_error_response(str(e))
    
    async def handle_test_analysis(self, message: Message) -> Message:
        """处理测试分析请求"""
        base = message.payload.get("base", "HEAD~1")
        changed_files = message.payload.get("changed_files", [])
        
        logger.info(f"{self.agent_id} 执行测试分析: base={base}")
        
        try:
            # 运行测试半径分析
            test_radius_result = await self.run_entrix_command(
                ["entrix", "graph", "test-radius", "--base", base, "--json"]
            )
            
            response = Message(
                from_agent=self.agent_id,
                payload={
                    "status": "success",
                    "test_radius": test_radius_result,
                    "changed_files": changed_files
                }
            )
            
        except Exception as e:
            response = self.create_error_response(str(e))
        
        return response
    
    async def run_entrix_command(self, command: List[str]) -> Dict[str, Any]:
        """运行 Entrix 命令"""
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, command, stdout, stderr
                )
            
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                result = {"raw_output": stdout}
            
            return result
            
        except Exception as e:
            logger.error(f"执行命令失败: {' '.join(command)}, 错误: {e}")
            raise
    
    def create_error_response(self, error_message: str) -> Message:
        """创建错误响应"""
        return Message(
            from_agent=self.agent_id,
            payload={
                "status": "error",
                "error": error_message
            }
        )