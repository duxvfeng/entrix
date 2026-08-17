"""
多智能体协作系统 - 消息总线实现
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型枚举"""
    QUALITY_CHECK_REQUEST = "quality_check_request"
    REVIEW_REQUEST = "review_request"
    TEST_ANALYSIS_REQUEST = "test_analysis_request"
    DOCUMENTATION_UPDATE_REQUEST = "documentation_update_request"
    AGGREGATION_REQUEST = "aggregation_request"
    RESPONSE = "response"
    ERROR = "error"


class Priority(Enum):
    """消息优先级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Message:
    """消息数据结构"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = ""
    to_agent: str = ""
    message_type: MessageType = MessageType.QUALITY_CHECK_REQUEST
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.MEDIUM
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    expires_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "type": self.message_type.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "expires_at": self.expires_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """从字典创建消息"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            from_agent=data.get("from_agent", ""),
            to_agent=data.get("to_agent", ""),
            message_type=MessageType(data.get("type", "quality_check_request")),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            payload=data.get("payload", {}),
            priority=Priority(data.get("priority", "medium")),
            correlation_id=data.get("correlation_id"),
            reply_to=data.get("reply_to"),
            expires_at=data.get("expires_at")
        )


class MessageBus:
    """消息总线 - 核心通信基础设施"""
    
    def __init__(self):
        self.queues: Dict[str, asyncio.Queue] = {}
        self.subscriptions: Dict[str, List[str]] = {}  # topic -> subscribers
        self.message_handlers: Dict[str, Callable] = {}  # agent_id -> handler
        self.dead_letter_queue: asyncio.Queue = asyncio.Queue()
        self.message_history: List[Message] = []
        self._running = False
        
    def register_agent(self, agent_id: str, handler: Callable) -> None:
        """注册智能体处理器"""
        self.message_handlers[agent_id] = handler
        self.queues[agent_id] = asyncio.Queue()
        logger.info(f"注册智能体: {agent_id}")
        
    def subscribe(self, agent_id: str, topic: str) -> None:
        """订阅主题"""
        if topic not in self.subscriptions:
            self.subscriptions[topic] = []
        if agent_id not in self.subscriptions[topic]:
            self.subscriptions[topic].append(agent_id)
            logger.info(f"{agent_id} 订阅主题: {topic}")
    
    async def publish(self, message: Message) -> None:
        """发布消息"""
        try:
            # 记录消息历史
            self.message_history.append(message)
            
            # 检查消息是否过期
            if message.expires_at:
                expires_at = datetime.fromisoformat(message.expires_at)
                if datetime.utcnow() > expires_at:
                    logger.warning(f"消息已过期: {message.id}")
                    await self.dead_letter_queue.put(message)
                    return
            
            # 直接发送到指定智能体
            if message.to_agent and message.to_agent in self.queues:
                await self.queues[message.to_agent].put(message)
                logger.debug(f"发送消息到 {message.to_agent}: {message.id}")
            else:
                logger.error(f"目标智能体不存在: {message.to_agent}")
                await self.dead_letter_queue.put(message)
                
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            await self.dead_letter_queue.put(message)
    
    async def subscribe_to_messages(self, agent_id: str) -> Message:
        """智能体接收消息"""
        if agent_id not in self.queues:
            raise ValueError(f"智能体未注册: {agent_id}")
        
        message = await self.queues[agent_id].get()
        return message
    
    async def request_response(self, message: Message, timeout: float = 30.0) -> Message:
        """发送请求并等待响应"""
        response_queue = asyncio.Queue()
        
        # 创建临时响应处理器
        response_future = asyncio.Future()
        
        async def response_handler():
            try:
                response = await asyncio.wait_for(
                    response_queue.get(), 
                    timeout=timeout
                )
                response_future.set_result(response)
            except asyncio.TimeoutError:
                response_future.set_exception(
                    TimeoutError(f"响应超时: {message.id}")
                )
        
        # 启动响应处理器
        response_task = asyncio.create_task(response_handler())
        
        # 发送请求
        message.reply_to = message.from_agent  # 响应发送回请求者
        await self.publish(message)
        
        try:
            response = await response_future
            return response
        finally:
            response_task.cancel()
    
    def get_message_history(self, agent_id: Optional[str] = None) -> List[Message]:
        """获取消息历史"""
        if agent_id:
            return [msg for msg in self.message_history 
                   if msg.from_agent == agent_id or msg.to_agent == agent_id]
        return self.message_history.copy()
    
    async def process_dead_letter_queue(self) -> None:
        """处理死信队列"""
        while not self.dead_letter_queue.empty():
            message = await self.dead_letter_queue.get()
            logger.warning(f"处理死信消息: {message.id}")
            # 这里可以实现重试逻辑或其他处理


class CircuitBreaker:
    """熔断器 - 防止级联失败"""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
        
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """通过熔断器调用函数"""
        if self.state == "open":
            if datetime.utcnow() - self.last_failure_time > timedelta(seconds=self.timeout):
                self.state = "half_open"
            else:
                raise Exception("熔断器打开状态")
        
        try:
            result = await func(*args, **kwargs)
            if self.state == "half_open":
                self.state = "closed"
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = datetime.utcnow()
            
            if self.failures >= self.failure_threshold:
                self.state = "open"
                logger.error(f"熔断器打开: {self.failures} 次失败")
            raise e


class AgentMetrics:
    """智能体指标收集"""
    
    def __init__(self):
        self.execution_times: Dict[str, List[float]] = {}
        self.success_counts: Dict[str, int] = {}
        self.error_counts: Dict[str, int] = {}
        self.message_counts: Dict[str, int] = {}
        
    def record_execution(self, agent_id: str, duration: float, success: bool) -> None:
        """记录执行数据"""
        if agent_id not in self.execution_times:
            self.execution_times[agent_id] = []
            self.success_counts[agent_id] = 0
            self.error_counts[agent_id] = 0
            self.message_counts[agent_id] = 0
        
        self.execution_times[agent_id].append(duration)
        self.message_counts[agent_id] += 1
        
        if success:
            self.success_counts[agent_id] += 1
        else:
            self.error_counts[agent_id] += 1
    
    def get_metrics(self, agent_id: str) -> Dict[str, Any]:
        """获取智能体指标"""
        if agent_id not in self.execution_times:
            return {}
        
        times = self.execution_times[agent_id]
        return {
            "agent_id": agent_id,
            "total_messages": self.message_counts[agent_id],
            "success_count": self.success_counts[agent_id],
            "error_count": self.error_counts[agent_id],
            "success_rate": self.success_counts[agent_id] / max(self.message_counts[agent_id], 1),
            "avg_execution_time": sum(times) / len(times) if times else 0,
            "max_execution_time": max(times) if times else 0,
            "min_execution_time": min(times) if times else 0
        }


# 全局消息总线实例
message_bus = MessageBus()
metrics = AgentMetrics()