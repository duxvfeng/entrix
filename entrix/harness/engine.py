"""Evidence collection engine."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Optional

from entrix.harness.conditions import WhenContext, evaluate_when
from entrix.harness.config import EvidenceProducerConfig, HarnessConfig
from entrix.harness.evidence import Evidence, EvidenceBundle
from entrix.harness.producers.base import ProducerContext
from entrix.harness.producers.builtin import (
    DiffStatsProducer,
    EntrixFitnessProducer,
    EntrixReviewTriggerProducer,
)
from entrix.harness.producers.command import CommandProducer
from entrix.harness.store import EvidenceStore


@dataclass
class HarnessRunContext:
    """Context for running harness evidence collection."""

    task_id: str
    repo_root: Path
    when_context: WhenContext
    attempt_id: str = "unknown"
    store: Optional[EvidenceStore] = None
    base_ref: str = "HEAD"
    parallel_producers: bool = False
    max_parallel_producers: int | None = None
    deadline: float | None = None


class EvidenceEngine:
    """Engine for collecting evidence based on harness configuration."""

    def __init__(self, config: HarnessConfig) -> None:
        """Initialize the evidence engine.

        Args:
            config: Harness configuration
        """
        self.config = config
        self._producer_registry = {
            "entrix-fitness": EntrixFitnessProducer,
            "entrix-review-trigger": EntrixReviewTriggerProducer,
            "diff-stats": DiffStatsProducer,
        }

    def collect(self, context: HarnessRunContext) -> EvidenceBundle:
        """Collect evidence based on configuration.

        Args:
            context: Harness run context

        Returns:
            EvidenceBundle containing collected evidence
        """
        # Check global when condition
        if not self.is_active(context):
            bundle = EvidenceBundle(
                task_id=context.task_id,
                attempt_id=context.attempt_id,
                active=False,
                evidence=[],
            )
            self._save_bundle(context, bundle)
            return bundle

        evidence_list: list[Evidence] = []
        collection_errors = []

        # Filter and execute producers
        active_producers = []
        for producer_config in self.config.evidence_producers:
            # Check producer-specific when condition
            if evaluate_when(producer_config.when, context.when_context):
                active_producers.append(producer_config)
            else:
                evidence_list.append(self._skipped_evidence(producer_config, context))

        max_workers = self._effective_max_workers(context)
        if max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._run_producer, producer_config, context): producer_config
                    for producer_config in active_producers
                }
                for future in as_completed(futures):
                    producer_config = futures[future]
                    try:
                        evidence_list.append(future.result())
                    except Exception as error:  # noqa: BLE001
                        collection_errors.append({"producer_id": producer_config.id, "error": str(error)})
        else:
            for producer_config in active_producers:
                if context.deadline is not None and context.deadline <= monotonic():
                    collection_errors.append(
                        {
                            "producer_id": producer_config.id,
                            "error": "Stop Gate deadline exceeded before producer start",
                        }
                    )
                    evidence_list.append(self._timeout_evidence(producer_config, context))
                    continue
                try:
                    evidence_list.append(self._run_producer(producer_config, context))
                except Exception as error:  # noqa: BLE001
                    collection_errors.append({"producer_id": producer_config.id, "error": str(error)})

        bundle = EvidenceBundle(
            task_id=context.task_id,
            attempt_id=context.attempt_id,
            evidence=evidence_list,
            collection_errors=collection_errors,
        )

        self._save_bundle(context, bundle)

        return bundle

    def _effective_max_workers(self, context: HarnessRunContext) -> int:
        """Return the bounded producer worker count for one collection."""
        if not context.parallel_producers:
            return 1
        if context.max_parallel_producers is None:
            return self.config.max_parallel_producers
        return min(context.max_parallel_producers, self.config.max_parallel_producers)

    @staticmethod
    def _skipped_evidence(
        producer_config: EvidenceProducerConfig, context: HarnessRunContext
    ) -> Evidence:
        return Evidence(
            id=producer_config.id,
            type=producer_config.type,
            name=producer_config.name,
            status="skipped",
            producer=producer_config.producer or producer_config.builtin or "harness",
            task_id=context.task_id,
            started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            raw={"reason": "when condition not met"},
        )

    @staticmethod
    def _timeout_evidence(
        producer_config: EvidenceProducerConfig, context: HarnessRunContext
    ) -> Evidence:
        return Evidence(
            id=producer_config.id,
            type=producer_config.type,
            name=producer_config.name,
            status="timeout",
            producer=producer_config.producer or producer_config.builtin or "harness",
            task_id=context.task_id,
            started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            raw={"error": "Stop Gate deadline exceeded before producer start"},
        )

    @staticmethod
    def _save_bundle(context: HarnessRunContext, bundle: EvidenceBundle) -> None:
        if context.store is not None:
            context.store.save(bundle)

    def _run_producer(self, producer_config: EvidenceProducerConfig, context: HarnessRunContext):
        producer = self._create_producer(producer_config)
        producer_context = ProducerContext(
            task_id=context.task_id,
            repo_root=context.repo_root,
            when_context=context.when_context,
            attempt_id=context.attempt_id,
            base_ref=context.base_ref,
            deadline=context.deadline,
        )
        return producer.run(producer_context)

    def is_active(self, context: HarnessRunContext) -> bool:
        """Return whether the global Harness condition applies to this run."""
        return evaluate_when(self.config.when, context.when_context)

    def _create_producer(self, config: EvidenceProducerConfig):
        """Create producer instance from configuration.

        Args:
            config: Producer configuration

        Returns:
            Producer instance
        """
        # Check if it's a builtin producer
        if config.builtin:
            producer_class = self._producer_registry.get(config.builtin)
            if producer_class:
                if config.builtin == "entrix-fitness":
                    return producer_class(config, self.config.fitness_dimensions)
                if config.builtin == "entrix-review-trigger":
                    return producer_class(config, self.config.review_trigger_rules)
                return producer_class(config)
            else:
                raise ValueError(f"Unknown builtin producer: {config.builtin}")

        # Default to command producer
        return CommandProducer(config)
