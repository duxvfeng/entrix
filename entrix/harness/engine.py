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
    parallel_producers: bool = True


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

        if context.parallel_producers:
            with ThreadPoolExecutor(max_workers=4) as executor:
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

        # Save bundle if store is provided
        if context.store:
            try:
                context.store.save(bundle)
            except Exception as e:
                collection_errors.append({"storage_error": str(e)})

        return bundle

    def _run_producer(self, producer_config: EvidenceProducerConfig, context: HarnessRunContext):
        producer = self._create_producer(producer_config)
        producer_context = ProducerContext(
            task_id=context.task_id,
            repo_root=context.repo_root,
            when_context=context.when_context,
            attempt_id=context.attempt_id,
            base_ref=context.base_ref,
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
