"""Short-lived workspace phase state used by the Claude Stop Hook."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from entrix.stop_gate.revalidation import _default_state_dir

PHASE_MODES = frozenset({"planning", "implementation", "init"})
DEFAULT_TTL_SECONDS = 8 * 60 * 60


def _phase_path(workspace: Path, session_id: str | None = None) -> Path:
    if not session_id:
        return workspace.resolve() / ".harness" / "runtime" / "phase.json"
    workspace_marker = hashlib.sha256(str(workspace.resolve()).encode("utf-8")).hexdigest()
    session_marker = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return _default_state_dir() / "phases" / workspace_marker / f"{session_marker}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def write_phase(
    workspace: Path,
    mode: str,
    *,
    one_shot: bool = False,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    session_id: str | None = None,
) -> None:
    """Atomically persist a short-lived phase marker for a workspace.

    Args:
        workspace: Repository workspace receiving the marker.
        mode: One of ``planning``, ``implementation`` or ``init``.
        one_shot: Whether the marker can be consumed once by the Stop Hook.
        ttl_seconds: Lifetime of the marker in seconds.

    Raises:
        ValueError: If the mode or lifetime is invalid.
        OSError: If the marker cannot be written.
    """
    if mode not in PHASE_MODES:
        raise ValueError(f"unknown phase mode: {mode}")
    if ttl_seconds < 0:
        raise ValueError("phase ttl_seconds must be non-negative")

    created_at = _now()
    payload: dict[str, Any] = {
        "schema_version": "stop-gate-phase/v1",
        "workspace": str(workspace.resolve()),
        "session_id": session_id or "",
        "mode": mode,
        "one_shot": one_shot,
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(seconds=ttl_seconds)).isoformat(),
    }
    path = _phase_path(workspace, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_phase(
    workspace: Path, session_id: str | None = None
) -> tuple[Path, dict[str, Any]] | None:
    path = _phase_path(workspace, session_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("phase state must be an object")
        if payload.get("schema_version") != "stop-gate-phase/v1":
            raise ValueError("unsupported phase state schema")
        if Path(str(payload.get("workspace"))).resolve() != workspace.resolve():
            raise ValueError("phase state workspace mismatch")
        if session_id and payload.get("session_id") != session_id:
            raise ValueError("phase state session mismatch")
        mode = payload.get("mode")
        if mode not in PHASE_MODES:
            raise ValueError("unsupported phase state mode")
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
        if expires_at <= _now():
            path.unlink(missing_ok=True)
            return None
        return path, payload
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def read_phase(workspace: Path, session_id: str | None = None) -> str | None:
    """Return the active phase mode, or ``None`` when no valid marker exists."""
    loaded = _load_phase(workspace, session_id)
    if loaded is None:
        return None
    return str(loaded[1]["mode"])


def clear_phase(workspace: Path, session_id: str | None = None) -> int:
    """Remove phase markers for one session and the legacy workspace marker.

    A session marker lives outside the repository, while older versions wrote a
    shared marker below ``.harness``. Clearing both makes the recovery command
    predictable after upgrading the plugin.
    """
    paths = {_phase_path(workspace)}
    workspace_marker = hashlib.sha256(str(workspace.resolve()).encode("utf-8")).hexdigest()
    session_root = _default_state_dir() / "phases" / workspace_marker
    if session_id:
        paths.add(_phase_path(workspace, session_id))
    elif session_root.is_dir():
        paths.update(session_root.glob("*.json"))

    removed = 0
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            continue
        removed += 1
    return removed


def consume_phase(workspace: Path, mode: str, session_id: str | None = None) -> bool:
    """Consume a matching one-shot marker and report whether it was consumed."""
    loaded = _load_phase(workspace, session_id)
    if loaded is None:
        return False
    path, payload = loaded
    if payload.get("mode") != mode or not payload.get("one_shot", False):
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True
