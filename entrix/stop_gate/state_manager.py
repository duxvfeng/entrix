"""会话状态管理器 - 混合存储策略"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from entrix.stop_gate.errors import SystemError
from entrix.stop_gate.model import AttemptState, AttemptStatus, GateAttempt


class SessionStateManager:
    """管理当前会话的活跃状态 - 混合存储策略"""

    def __init__(self, state_dir: Path | None = None):
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
        self.session_id = str(uuid4())
        self.started_at = datetime.now(timezone.utc)
        self.total_attempts = 0
        self.passed_attempts = 0
        self.failed_attempts = 0

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
                attempt_data=attempt,
            )

            self.active_attempts[attempt_id] = state
            self.total_attempts += 1

            # 同步到文件系统
            self._persist_state()

            return attempt_id

    def update_attempt_status(
        self,
        attempt_id: str,
        status: AttemptStatus,
        verdict: dict[str, Any] | None = None,
        evidence_pack_path: Path | None = None,
    ) -> None:
        """更新尝试状态并同步"""
        with self.lock:
            if attempt_id not in self.active_attempts:
                raise ValueError(f"Attempt {attempt_id} 不存在")

            state = self.active_attempts[attempt_id]
            state.status = status
            state.updated_at = datetime.now(timezone.utc)

            if verdict is not None:
                state.verdict = verdict
            if evidence_pack_path is not None:
                state.evidence_pack_path = evidence_pack_path

            # 更新统计
            if status == AttemptStatus.PASSED:
                self.passed_attempts += 1
            elif status == AttemptStatus.FAILED:
                self.failed_attempts += 1

            # 同步到文件系统
            self._persist_state()

    def get_attempt(self, attempt_id: str) -> AttemptState | None:
        """获取尝试状态 - 优先从内存读取"""
        with self.lock:
            return self.active_attempts.get(attempt_id)

    def cleanup_expired_attempts(self, max_age_hours: int = 24) -> list[str]:
        """清理过期的尝试状态"""
        with self.lock:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            expired = [
                attempt_id
                for attempt_id, state in self.active_attempts.items()
                if state.created_at < cutoff
            ]

            for attempt_id in expired:
                del self.active_attempts[attempt_id]

            if expired:
                self._persist_state()

            return expired

    def _persist_state(self) -> None:
        """持久化状态到文件系统"""
        try:
            state_data = {
                "schema_version": "session-state.v1",
                "session_id": self.session_id,
                "started_at": self.started_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "active_attempts": {
                    attempt_id: self._state_to_dict(state)
                    for attempt_id, state in self.active_attempts.items()
                },
                "session_stats": {
                    "total_attempts": self.total_attempts,
                    "passed_attempts": self.passed_attempts,
                    "failed_attempts": self.failed_attempts,
                },
            }

            # 原子写入：先写临时文件，再重命名
            temp_file = self.state_file.with_suffix(".tmp")
            temp_file.write_text(json.dumps(state_data, indent=2), encoding="utf-8")
            temp_file.replace(self.state_file)

        except OSError as e:
            raise SystemError(f"状态持久化失败: {e}")

    def _recover_from_disk(self) -> None:
        """从磁盘恢复状态"""
        if not self.state_file.exists():
            return

        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))

            # 恢复会话统计
            self.session_id = data.get("session_id", self.session_id)
            self.total_attempts = data.get("session_stats", {}).get("total_attempts", 0)
            self.passed_attempts = data.get("session_stats", {}).get("passed_attempts", 0)
            self.failed_attempts = data.get("session_stats", {}).get("failed_attempts", 0)

            started_at_str = data.get("started_at")
            if started_at_str:
                self.started_at = datetime.fromisoformat(started_at_str)

            # 恢复活跃尝试
            for attempt_id, state_data in data.get("active_attempts", {}).items():
                state = self._state_from_dict(state_data)
                self.active_attempts[attempt_id] = state

        except (json.JSONDecodeError, OSError, ValueError) as e:
            # 恢复失败，使用干净状态
            print(f"状态恢复失败: {e}，使用干净状态")

    def _state_to_dict(self, state: AttemptState) -> dict[str, Any]:
        """将 AttemptState 转换为可序列化的字典"""
        result = asdict(state)
        result["status"] = state.status.value
        result["created_at"] = state.created_at.isoformat()
        if state.updated_at:
            result["updated_at"] = state.updated_at.isoformat()
        if state.attempt_data:
            result["attempt_data"] = self._attempt_to_dict(state.attempt_data)
        if state.evidence_pack_path:
            result["evidence_pack_path"] = str(state.evidence_pack_path)
        if state.verdict:
            result["verdict"] = self._verdict_to_dict(state.verdict)
        return result

    def _state_from_dict(self, data: dict[str, Any]) -> AttemptState:
        """从字典恢复 AttemptState"""
        attempt_data = data.get("attempt_data")
        if attempt_data:
            attempt_data = self._attempt_from_dict(attempt_data)

        verdict = data.get("verdict")
        if verdict:
            verdict = self._verdict_from_dict(verdict)

        evidence_pack_path = data.get("evidence_pack_path")
        if evidence_pack_path:
            evidence_pack_path = Path(evidence_pack_path)

        return AttemptState(
            attempt_id=data["attempt_id"],
            status=AttemptStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            attempt_data=attempt_data,
            verdict=verdict,
            evidence_pack_path=evidence_pack_path,
        )

    def _attempt_to_dict(self, attempt: GateAttempt) -> dict[str, Any]:
        """将 GateAttempt 转换为可序列化的字典"""
        result = asdict(attempt)
        result["workspace"] = str(attempt.workspace)
        result["requested_at"] = attempt.requested_at.isoformat()
        return result

    def _attempt_from_dict(self, data: dict[str, Any]) -> GateAttempt:
        """从字典恢复 GateAttempt"""
        return GateAttempt(
            attempt_id=data["attempt_id"],
            session_id=data["session_id"],
            task_id=data["task_id"],
            workspace=Path(data["workspace"]),
            base_ref=data.get("base_ref"),
            changed_files=data["changed_files"],
            requested_at=datetime.fromisoformat(data["requested_at"]),
            stop_reason=data["stop_reason"],
        )

    def _verdict_to_dict(self, verdict: dict[str, Any]) -> dict[str, Any]:
        """将 verdict 字典转换为可序列化形式"""
        result = dict(verdict)
        if "decided_at" in result and isinstance(result["decided_at"], datetime):
            result["decided_at"] = result["decided_at"].isoformat()
        return result

    def _verdict_from_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """从字典恢复 verdict"""
        result = dict(data)
        if "decided_at" in result and isinstance(result["decided_at"], str):
            result["decided_at"] = datetime.fromisoformat(result["decided_at"])
        return result
