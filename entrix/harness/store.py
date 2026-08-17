"""Evidence bundle persistence layer."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin, get_type_hints
from uuid import uuid4

from entrix.harness.evidence import EvidenceBundle

T = TypeVar("T")


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
        target_task_id = task_id if task_id is not None else bundle.task_id
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
                json.dump(asdict(bundle), file, indent=2, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            temporary_path.replace(filepath)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

        return filepath

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
    for field in fields(cls):
        name = field.name
        if name not in data:
            continue
        field_type = type_hints.get(name, field.type)
        converted[name] = _convert_value(data[name], field_type)
    return cls(**converted)


def _convert_value(value: Any, field_type: Any) -> Any:
    """Convert a deserialized value to the expected dataclass field type."""
    if is_dataclass(field_type) and isinstance(value, dict):
        return _dict_to_dataclass(field_type, value)

    origin = get_origin(field_type)
    args = get_args(field_type)

    if origin is list and args:
        item_type = args[0]
        return [_convert_value(item, item_type) for item in value]

    if origin is dict:
        return dict(value)

    return value
