"""Gate policy data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    """Gate policy severity levels."""

    HARD = "hard"
    SOFT = "soft"
    ADVISORY = "advisory"
    BLOCKED = "blocked"


@dataclass
class GateRule:
    """Single gate rule for evaluating evidence."""

    name: str = ""
    evidence_id: str | None = None
    evidence_type: str | None = None
    condition: str = ""
    action: str | None = None


@dataclass
class GatePolicy:
    """Policy containing one or more gate rules."""

    name: str = ""
    severity: Severity = Severity.HARD
    rule: GateRule = field(default_factory=GateRule)
    when: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.rule is None or isinstance(self.rule, dict):
            self.rule = GateRule(**(self.rule if isinstance(self.rule, dict) else {}))
