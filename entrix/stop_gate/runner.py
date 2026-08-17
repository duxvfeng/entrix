"""Harness runner for Stop hook integration."""

from pathlib import Path
from typing import Any

from entrix.harness.conditions import WhenContext
from entrix.harness.config import load_harness_config
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.gate.arbiter import GateEngine, Verdict, VerdictStatus
from entrix.harness.store import EvidenceStore


class HarnessRunner:
    """Run the configured Harness flow without initializing the legacy Stop Gate."""

    def __init__(
        self,
        config_path: Path,
        *,
        evidence_root: Path | None = None,
        parallel_producers: bool = False,
    ) -> None:
        self.config_path = config_path
        self.evidence_root = evidence_root
        self.parallel_producers = parallel_producers

    def run(self, context: dict[str, Any]) -> Verdict:
        """Collect evidence and arbitrate the configured Harness policies."""
        config = load_harness_config(self.config_path)
        workspace = Path(context.get("workspace") or context["repo_path"])
        task_id = str(context.get("task_id") or context.get("session_id") or "unknown-session")
        harness_context = HarnessRunContext(
            task_id=task_id,
            attempt_id=str(context.get("attempt_id") or task_id),
            repo_root=workspace,
            when_context=WhenContext(
                repo_root=workspace,
                changed_files=list(context.get("changed_files") or []),
                current_branch=str(context.get("branch") or "unknown"),
            ),
            store=EvidenceStore(self.evidence_root or workspace),
            base_ref=str(context.get("base_ref") or "HEAD"),
            parallel_producers=self.parallel_producers,
        )
        evidence_engine = EvidenceEngine(config)
        bundle = evidence_engine.collect(harness_context)
        if not bundle.active:
            return Verdict(
                status=VerdictStatus.PASS,
                summary="Harness inactive for current context",
            )
        return GateEngine(config.gate_policies).arbitrate(
            bundle, harness_context.when_context
        )
