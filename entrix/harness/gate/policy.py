"""Gate policy data structures."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional


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
    evidence_id: Optional[str] = None
    evidence_type: Optional[str] = None
    condition: str = ""
    action: Optional[str] = None


@dataclass
class GatePolicy:
    """Policy containing one or more gate rules."""

    name: str = ""
    severity: Severity = Severity.HARD
    rule: GateRule = field(default_factory=GateRule)

    def __post_init__(self):
        if self.rule is None or isinstance(self.rule, dict):
            self.rule = GateRule(**(self.rule if isinstance(self.rule, dict) else {}))