"""Stop Gate 错误处理系统"""

from __future__ import annotations

from datetime import datetime, timezone


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

    def __init__(self, message: str):
        super().__init__(message, recoverable=False)


class EvidenceCollectionError(ExecutionError):
    """证据收集失败"""

    def __init__(self, component: str, message: str):
        self.component = component
        full_message = f"{component}: {message}"
        super().__init__(full_message)


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
