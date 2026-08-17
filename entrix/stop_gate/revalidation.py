"""Persistent state for change-aware Stop Gate revalidation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachedVerdict:
    """A Stop Gate verdict associated with one workspace snapshot."""

    fingerprint: str
    status: str
    summary: str


class StopGateStateStore:
    """Persist the last verdict for each Claude session outside the workspace."""

    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or Path(tempfile.gettempdir()) / "harness-monitor" / "stop-gate"

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

    def evidence_root(self, workspace: Path) -> Path:
        """Return the external EvidenceStore root for a workspace."""
        root = self.state_dir / "evidence" / self._workspace_marker(workspace)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _path(self, workspace: Path, session_id: str) -> Path:
        session_marker = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return self.state_dir / "sessions" / self._workspace_marker(workspace) / f"{session_marker}.json"

    @staticmethod
    def _workspace_marker(workspace: Path) -> str:
        return hashlib.sha256(str(workspace.resolve()).encode("utf-8")).hexdigest()
