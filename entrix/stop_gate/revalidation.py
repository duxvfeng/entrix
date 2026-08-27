"""Persistent state for change-aware Stop Gate revalidation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

RETENTION_DAYS = 30
MAX_SESSIONS_PER_WORKSPACE = 50


@dataclass(frozen=True)
class CachedVerdict:
    """A Stop Gate verdict associated with one workspace snapshot."""

    fingerprint: str
    status: str
    summary: str


class StopGateStateStore:
    """Persist verdicts and evidence outside the checked workspace."""

    def __init__(self, state_dir: Path | None = None) -> None:
        # 容忍 argparse 等来源传入的 str 路径。 The workspace is never a
        # default storage location: Stop hooks must not dirty the repository.
        self.state_dir = (
            Path(state_dir)
            if state_dir
            else _default_state_dir()
        )

    def load(self, workspace: Path, session_id: str) -> CachedVerdict | None:
        """Return the last valid verdict for a workspace and Claude session."""
        try:
            payload = json.loads(self._path(workspace, session_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        fingerprint = payload.get("fingerprint")
        status = payload.get("status")
        summary = payload.get("summary")
        if not isinstance(fingerprint, str):
            return None
        if not isinstance(status, str):
            return None
        if not isinstance(summary, str):
            return None
        return CachedVerdict(fingerprint=fingerprint, status=status, summary=summary)

    def save(self, workspace: Path, session_id: str, verdict: CachedVerdict) -> None:
        """Atomically persist a verdict without modifying the checked repository."""
        target = self._path(workspace, session_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{os.getpid()}.tmp")
        payload = {
            "schema_version": "stop-gate-state/v1",
            "fingerprint": verdict.fingerprint,
            "status": verdict.status,
            "summary": verdict.summary,
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(target)
        try:
            self._prune_sessions(target.parent)
        except OSError:
            # 剪枝失败不影响本次保存已成功的事实
            pass

    def delete(self, workspace: Path, session_id: str) -> None:
        """Delete cached authorization state for one workspace session."""
        self._path(workspace, session_id).unlink(missing_ok=True)

    def _prune_sessions(self, sessions_dir: Path) -> None:
        """删除过期或超出数量上限的 session verdict 文件。"""
        sessions = sorted(
            (path for path in sessions_dir.glob("*.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        cutoff = time.time() - RETENTION_DAYS * 86400
        for index, path in enumerate(sessions):
            try:
                if path.stat().st_mtime < cutoff or index >= MAX_SESSIONS_PER_WORKSPACE:
                    path.unlink(missing_ok=True)
            except OSError:
                continue

    def evidence_root(self, workspace: Path) -> Path:
        """Return the external EvidenceStore root for a workspace."""
        root = self.state_dir / "evidence" / self._workspace_marker(workspace)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def trust_config(self, workspace: Path, config_path: Path) -> None:
        """Record explicit user approval for the current Harness config hash."""
        target = self._trust_path(workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "stop-gate-trust/v1",
            "workspace": str(workspace.resolve()),
            "config": str(config_path.resolve()),
            "config_sha256": _file_sha256(config_path),
        }
        temporary = target.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(target)

    def is_config_trusted(self, workspace: Path, config_path: Path) -> bool:
        """Return whether the exact current config was explicitly approved."""
        try:
            payload = json.loads(self._trust_path(workspace).read_text(encoding="utf-8"))
            return (
                isinstance(payload, dict)
                and payload.get("schema_version") == "stop-gate-trust/v1"
                and payload.get("workspace") == str(workspace.resolve())
                and payload.get("config") == str(config_path.resolve())
                and payload.get("config_sha256") == _file_sha256(config_path)
            )
        except (OSError, json.JSONDecodeError, ValueError):
            return False

    def sessions_dir(self, workspace: Path) -> Path:
        """Return the directory holding cached verdicts for a workspace."""
        return self.state_dir / "sessions" / self._workspace_marker(workspace)

    def _path(self, workspace: Path, session_id: str) -> Path:
        session_marker = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return self.state_dir / "sessions" / self._workspace_marker(workspace) / f"{session_marker}.json"

    def _trust_path(self, workspace: Path) -> Path:
        return self.state_dir / "trust" / f"{self._workspace_marker(workspace)}.json"

    @staticmethod
    def _workspace_marker(workspace: Path) -> str:
        return hashlib.sha256(str(workspace.resolve()).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _default_state_dir() -> Path:
    """Return a user-scoped cache directory on the current platform."""
    configured = os.environ.get("ENTRIX_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(root) / "entrix" / "stop-gate"
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home) / "entrix" / "stop-gate"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "entrix" / "stop-gate"
    return Path.home() / ".local" / "state" / "entrix" / "stop-gate"
