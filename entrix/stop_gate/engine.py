"""Stop Gate Engine - 核心编排引擎"""

from __future__ import annotations

import logging
from pathlib import Path

from entrix.stop_gate.arbiter import GateArbiter
from entrix.stop_gate.collector import EvidenceCollector
from entrix.stop_gate.errors import StopGateError
from entrix.stop_gate.formatter import FeedbackFormatter
from entrix.stop_gate.model import AttemptState, AttemptStatus, GateAttempt, StopDecision
from entrix.stop_gate.state_manager import SessionStateManager

logger = logging.getLogger(__name__)


class StopGateEngine:
    """Stop Gate 核心引擎 - 编排所有组件"""

    def __init__(self, state_dir: Path | None = None, timeout_seconds: int = 300):
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
            logger.info("收集证据: %s", attempt.attempt_id)
            evidence_pack = self.collector.collect_evidence(attempt)

            # 3. 更新为裁决状态
            self.state_manager.update_attempt_status(attempt.attempt_id, AttemptStatus.ARBITRATING)

            # 4. 裁决
            logger.info("执行裁决: %s", attempt.attempt_id)
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
                    "summary": verdict.summary,
                },
                evidence_pack_path=feedback.artifact_path,
            )

            # 7. 生成决策结果
            allow_stop = verdict.verdict == "PASS"

            return StopDecision(
                allow_stop=allow_stop,
                feedback=feedback.user_readable,
                attempt_id=attempt.attempt_id,
                verdict=verdict,
            )

        except StopGateError as e:
            logger.error("处理 Stop 请求时发生错误: %s", e)
            return self._error_decision(attempt, e)
        except Exception as e:
            logger.exception("未预期的错误")
            return self._error_decision(attempt, e)

    def get_attempt_history(self, session_id: str) -> list[AttemptState]:
        """获取会话的历史尝试"""
        return [
            state
            for state in self.state_manager.active_attempts.values()
            if state.attempt_data is not None and state.attempt_data.session_id == session_id
        ]

    def cleanup(self, max_age_hours: int = 24) -> None:
        """清理过期状态"""
        self.state_manager.cleanup_expired_attempts(max_age_hours)

    def _verdict_to_status(self, verdict: str) -> AttemptStatus:
        """将裁决转换为状态"""
        mapping = {
            "PASS": AttemptStatus.PASSED,
            "FAIL": AttemptStatus.FAILED,
            "BLOCKED": AttemptStatus.BLOCKED,
        }
        return mapping.get(verdict, AttemptStatus.BLOCKED)

    def _error_decision(self, attempt: GateAttempt, error: Exception) -> StopDecision:
        """生成错误决策"""
        error_message = f"处理 Stop 请求时发生错误: {error}"

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
            verdict=None,
        )
