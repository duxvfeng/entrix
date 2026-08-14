"""Stop Gate Adapter - Claude Code 插件集成接口"""

from __future__ import annotations

import logging
from pathlib import Path

from entrix.stop_gate.engine import StopGateEngine
from entrix.stop_gate.model import GateAttempt, StopDecision

logger = logging.getLogger(__name__)


class StopGateAdapter:
    """Claude Code 插件适配器 - 接入插件生命周期"""

    def __init__(self, state_dir: Path | None = None, timeout_seconds: int = 300):
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
                stop_reason=session_context.get("stop_reason", "unknown"),
                base_ref=session_context.get("base_ref"),
            )

            logger.info("处理 Stop 请求: %s", attempt.attempt_id)

            # 3. 调用引擎处理
            decision = self.engine.process_stop_request(attempt)

            return decision

        except Exception as e:
            logger.exception("适配器处理失败")
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
{error}

## 建议操作
1. 检查日志获取详细错误信息
2. 确认所有依赖正确安装
3. 如问题持续，请联系支持

🔄 系统状态: ADAPTER_ERROR - 阻止任务结束""",
            attempt_id="error",
            verdict=None,
        )
