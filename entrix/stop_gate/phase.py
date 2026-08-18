"""Short-lived workspace phase state used by the Claude Stop Hook."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PHASE_MODES = frozenset({"planning", "implementation", "init"})
DEFAULT_TTL_SECONDS = 8 * 60 * 60


def _phase_path(workspace: Path) -> Path:
    return workspace.resolve() / ".harness" / "runtime" / "phase.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def write_phase(
    workspace: Path,
    mode: str,
    *,
    one_shot: bool = False,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
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
        "mode": mode,
        "one_shot": one_shot,
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(seconds=ttl_seconds)).isoformat(),
    }
    path = _phase_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_phase(workspace: Path) -> tuple[Path, dict[str, Any]] | None:
    path = _phase_path(workspace)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("phase state must be an object")
        if payload.get("schema_version") != "stop-gate-phase/v1":
            raise ValueError("unsupported phase state schema")
        if Path(str(payload.get("workspace"))).resolve() != workspace.resolve():
            raise ValueError("phase state workspace mismatch")
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


def read_phase(workspace: Path) -> str | None:
    """Return the active phase mode, or ``None`` when no valid marker exists."""
    loaded = _load_phase(workspace)
    if loaded is None:
        return None
    return str(loaded[1]["mode"])


def consume_phase(workspace: Path, mode: str) -> bool:
    """Consume a matching one-shot marker and report whether it was consumed."""
    loaded = _load_phase(workspace)
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
