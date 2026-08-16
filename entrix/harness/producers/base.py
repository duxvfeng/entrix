"""Producer protocol and context."""
from dataclasses import dataclass
from pathlib import Path
from entrix.harness.conditions import WhenContext
from entrix.harness.evidence import Evidence

@dataclass
class ProducerContext:
    """Context provided to producers at runtime."""
    task_id: str
    repo_root: Path
    when_context: WhenContext
    attempt_id: str = "unknown"

class Producer:
    """Evidence producer protocol.

    Producers collect evidence through some mechanism (command, builtin, etc.)
    and return it as Evidence objects.
    """

    def run(self, context: ProducerContext) -> Evidence:
        """Execute the producer and return evidence.

        Args:
            context: Execution context

        Returns:
            Evidence object containing the results
        """
        raise NotImplementedError("Producer.run must be implemented by subclasses")