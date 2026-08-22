"""Harness runner for Stop hook integration."""

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from entrix.harness.conditions import WhenContext
from entrix.harness.config import load_harness_config
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.evidence import EvidenceBundle
from entrix.harness.gate.arbiter import GateEngine, Verdict, VerdictStatus
from entrix.harness.store import EvidenceStore


@dataclass
class RunResult:
    """Result of one Harness run for the Stop hook."""

    verdict: Verdict
    bundle: EvidenceBundle | None = None
    bundle_path: Path | None = None


class HarnessRunner:
    """Run the configured Harness flow without initializing the legacy Stop Gate."""

    def __init__(
        self,
        config_path: Path,
        *,
        evidence_root: Path | None = None,
        parallel_producers: bool = False,
        timeout_seconds: int | float | None = None,
    ) -> None:
        self.config_path = config_path
        self.evidence_root = evidence_root
        self.parallel_producers = parallel_producers
        self.timeout_seconds = timeout_seconds

    def run(self, context: dict[str, Any]) -> RunResult:
        """Collect evidence and arbitrate the configured Harness policies."""
        config = load_harness_config(self.config_path)
        workspace = Path(context.get("workspace") or context["repo_path"])
        task_id = str(context.get("task_id") or context.get("session_id") or "unknown-session")
        deadline = (
            monotonic() + float(self.timeout_seconds)
            if self.timeout_seconds is not None
            else None
        )
        harness_context = HarnessRunContext(
            task_id=task_id,
            attempt_id=str(context.get("attempt_id") or task_id),
            repo_root=workspace,
            when_context=WhenContext(
                repo_root=workspace,
                changed_files=list(context.get("changed_files") or []),
                current_branch=str(context.get("branch") or "unknown"),
            ),
            store=None,
            base_ref=str(context.get("base_ref") or "HEAD"),
            parallel_producers=self.parallel_producers,
            deadline=deadline,
        )
        evidence_engine = EvidenceEngine(config)
        bundle = evidence_engine.collect(harness_context)
        store = EvidenceStore(self.evidence_root or workspace)
        bundle_path = store.save(bundle, task_id=task_id)
        if not bundle.active:
            return RunResult(
                verdict=Verdict(
                    status=VerdictStatus.PASS,
                    summary="Harness inactive for current context",
                ),
                bundle=bundle,
                bundle_path=bundle_path,
            )
        verdict = GateEngine(config.gate_policies).arbitrate(
            bundle, harness_context.when_context
        )
        return RunResult(verdict=verdict, bundle=bundle, bundle_path=bundle_path)
