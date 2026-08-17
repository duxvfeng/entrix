"""Evidence collection engine."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from entrix.harness.config import HarnessConfig, EvidenceProducerConfig
from entrix.harness.conditions import WhenContext, evaluate_when
from entrix.harness.store import EvidenceStore
from entrix.harness.evidence import EvidenceBundle
from entrix.harness.producers.base import ProducerContext
from entrix.harness.producers.command import CommandProducer
from entrix.harness.producers.builtin import (
    EntrixFitnessProducer,
    EntrixReviewTriggerProducer,
    DiffStatsProducer,
)


@dataclass
class HarnessRunContext:
    """Context for running harness evidence collection."""

    task_id: str
    repo_root: Path
    when_context: WhenContext
    attempt_id: str = "unknown"
    store: Optional[EvidenceStore] = None
    base_ref: str = "HEAD"


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
            return EvidenceBundle(
                task_id=context.task_id,
                attempt_id=context.attempt_id,
                evidence=[],
                collection_errors=[{"message": "Global when condition not met"}],
            )

        evidence_list = []
        collection_errors = []

        # Filter and execute producers
        active_producers = []
        for producer_config in self.config.evidence_producers:
            # Check producer-specific when condition
            if evaluate_when(producer_config.when, context.when_context):
                active_producers.append(producer_config)

        # Execute producers in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_producer = {}

            for producer_config in active_producers:
                producer = self._create_producer(producer_config)
                producer_context = ProducerContext(
                    task_id=context.task_id,
                    repo_root=context.repo_root,
                    when_context=context.when_context,
                    attempt_id=context.attempt_id,
                    base_ref=context.base_ref,
                )

                future = executor.submit(producer.run, producer_context)
                future_to_producer[future] = producer_config

            for future in as_completed(future_to_producer):
                producer_config = future_to_producer[future]
                try:
                    evidence = future.result()
                    evidence_list.append(evidence)
                except Exception as e:
                    collection_errors.append({"producer_id": producer_config.id, "error": str(e)})

        bundle = EvidenceBundle(
            task_id=context.task_id,
            attempt_id=context.attempt_id,
            evidence=evidence_list,
            collection_errors=collection_errors,
        )

        # Save bundle if store is provided
        if context.store:
            try:
                context.store.save(bundle)
            except Exception as e:
                collection_errors.append({"storage_error": str(e)})

        return bundle

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
                return producer_class(config)
            else:
                raise ValueError(f"Unknown builtin producer: {config.builtin}")

        # Default to command producer
        return CommandProducer(config)
