"""Harness runner for stop-gate integration."""
from pathlib import Path
from typing import Dict, Any

from entrix.harness.config import load_harness_config
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.gate.arbiter import GateEngine
from entrix.harness.store import EvidenceStore
from entrix.stop_gate.adapter import StopGateAdapter


class HarnessRunner:
    """Runner that executes the harness flow in stop-gate context."""

    def __init__(self, config_path: Path) -> None:
        """Initialize the harness runner.

        Args:
            config_path: Path to harness.yaml configuration
        """
        self.config_path = config_path
        self.config = None
        self.adapter = StopGateAdapter()

    def run(self, context: Dict[str, Any]) -> Any:
        """Execute the complete harness flow.

        Args:
            context: Hook payload dictionary

        Returns:
            Verdict from gate arbitration
        """
        # Load configuration
        self.config = load_harness_config(self.config_path)

        # Adapt payload to harness context
        harness_context = self.adapter.adapt_payload(context)

        # Collect evidence
        evidence_engine = EvidenceEngine(self.config)
        bundle = evidence_engine.collect(harness_context)

        # Arbitrate gates
        gate_engine = GateEngine(self.config.gate_policies)
        verdict = gate_engine.arbitrate(bundle)

        return verdict