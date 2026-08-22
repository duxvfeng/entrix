"""Evidence bundle persistence layer."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar, cast, get_args, get_origin, get_type_hints
from uuid import uuid4

from entrix.harness.evidence import EvidenceBundle

T = TypeVar("T")

_MAX_PERSISTED_TEXT = 4000
_SECRET_KEY = re.compile(r"(?:password|passwd|secret|token|api[_-]?key|authorization)", re.I)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|authorization)\b\s*[:=]\s*)([^\s,;]+)"
)


def _validated_task_id(task_id: object) -> str:
    """Accept only one non-empty path segment for an Evidence task directory."""
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id 必须是非空安全路径段")
    task_path = Path(task_id)
    if (
        task_path.is_absolute()
        or len(task_path.parts) != 1
        or task_path.name != task_id
        or task_id in {".", ".."}
    ):
        raise ValueError("task_id 必须是非空安全路径段")
    return task_id


class EvidenceStore:
    """Manage persistence of evidence bundles to disk."""

    def __init__(self, root_dir: Path) -> None:
        """Initialize the store.

        Args:
            root_dir: Root directory under which ``.harness/evidence`` will live.
        """
        self.root_dir = root_dir
        self.evidence_dir = root_dir / ".harness" / "evidence"

    def save(self, bundle: EvidenceBundle, task_id: str | None = None) -> Path:
        """Persist an evidence bundle to disk.

        The bundle is written to ``.harness/evidence/<task_id>/<timestamp>-bundle.json``.

        Args:
            bundle: The evidence bundle to persist.
            task_id: Optional task identifier. When omitted, ``bundle.task_id`` is used.

        Returns:
            The path of the written bundle file.
        """
        target_task_id = _validated_task_id(task_id if task_id is not None else bundle.task_id)
        task_dir = self.evidence_dir / target_task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"{timestamp}-bundle.json"
        filepath = task_dir / filename

        # Guard against two saves landing in the same millisecond.
        if filepath.exists():
            for counter in range(1, 1000):
                candidate = task_dir / f"{timestamp}-{counter}-bundle.json"
                if not candidate.exists():
                    filepath = candidate
                    break
            else:
                raise OSError("Unable to generate a unique evidence bundle filename")

        temporary_path = task_dir / f".{filepath.name}.{uuid4().hex}.tmp"
        try:
            with temporary_path.open("x", encoding="utf-8") as file:
                json.dump(_sanitize_value(asdict(bundle)), file, indent=2, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            temporary_path.replace(filepath)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

        try:
            self.prune(target_task_id)
        except OSError:
            # Retention is best-effort; a successful gate must not become a
            # failure only because an old diagnostic file cannot be removed.
            pass
        return filepath

    def prune(self, task_id: str, *, keep: int = 20) -> int:
        """Remove old bundles for one task and return the number removed."""
        task_dir = self.evidence_dir / _validated_task_id(task_id)
        bundles = sorted(task_dir.glob("*-bundle.json"), key=lambda path: path.name)
        removed = 0
        for path in bundles[:-max(1, keep)]:
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
        return removed

    def load(self, path: Path) -> EvidenceBundle | None:
        """Load an evidence bundle from disk.

        Args:
            path: Path to a previously saved bundle file.

        Returns:
            The reconstructed ``EvidenceBundle`` or ``None`` if loading fails.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(data, dict):
            return None

        try:
            return _dict_to_dataclass(EvidenceBundle, data)
        except (TypeError, ValueError):
            return None


def _dict_to_dataclass(cls: type[T], data: dict[str, Any]) -> T:
    """Reconstruct a dataclass instance from a plain dictionary."""
    type_hints = get_type_hints(cls)
    converted: dict[str, Any] = {}
    # Dataclass reflection is dynamic; JSON values are normalized below.
    for field in fields(cast(Any, cls)):
        name = field.name
        if name not in data:
            continue
        field_type = type_hints.get(name, field.type)
        converted[name] = _convert_value(data[name], field_type)
    return cls(**converted)


def _sanitize_value(value: Any, *, key: str = "") -> Any:
    """Bound persisted output and redact common credential-shaped values."""
    if isinstance(value, str):
        if key and _SECRET_KEY.search(key):
            return "<redacted>"
        redacted = _SECRET_ASSIGNMENT.sub(r"\1<redacted>", value)
        if len(redacted) <= _MAX_PERSISTED_TEXT:
            return redacted
        return f"{redacted[:_MAX_PERSISTED_TEXT]}... [truncated]"
    if isinstance(value, dict):
        return {str(name): _sanitize_value(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    return value


def _convert_value(value: Any, field_type: Any) -> Any:
    """Convert a deserialized value to the expected dataclass field type."""
    if is_dataclass(field_type) and isinstance(value, dict):
        return _dict_to_dataclass(cast(type[Any], field_type), value)

    origin = get_origin(field_type)
    args = get_args(field_type)

    if origin is list and args:
        item_type = args[0]
        return [_convert_value(item, item_type) for item in value]

    if origin is dict:
        return dict(value)

    return value
