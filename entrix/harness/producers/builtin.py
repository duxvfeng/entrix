"""Builtin evidence producers for Entrix-specific functionality."""

import subprocess
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from time import monotonic
from typing import Any

from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.evidence import Evidence
from entrix.harness.producers.base import Producer, ProducerContext
from entrix.model import Dimension
from entrix.review_trigger import ReviewTriggerRule


def _serialize_for_json(obj: Any) -> Any:
    """Convert an object to a JSON-serializable representation.

    This handles dataclasses, enums, lists, and dicts recursively.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialize_for_json(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    return obj


def _new_evidence(config: EvidenceProducerConfig, producer: str, context: ProducerContext) -> Evidence:
    return Evidence(
        id=config.id,
        type=config.type,
        name=config.name,
        producer=producer,
        task_id=context.task_id,
        started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def _finish_evidence(evidence: Evidence, started: float) -> Evidence:
    evidence.duration_ms = max(0, int((monotonic() - started) * 1000))
    return evidence


class EntrixFitnessProducer(Producer):
    """Produce fitness evidence through Entrix's shared fitness engine."""

    def __init__(self, config: EvidenceProducerConfig, dimensions: list[Dimension]) -> None:
        self.config = config
        self.dimensions = dimensions

    def run(self, context: ProducerContext) -> Evidence:
        started = monotonic()
        evidence = _new_evidence(self.config, "entrix-fitness", context)
        try:
            from entrix.engine import run_fitness_report
            from entrix.governance import GovernancePolicy
            from entrix.presets import get_project_preset

            report, _dimensions = run_fitness_report(
                context.repo_root,
                GovernancePolicy(),
                get_project_preset(),
                dimensions=self.dimensions,
                changed_files=context.when_context.changed_files,
                base=context.base_ref,
                deadline=context.deadline,
            )
            evidence.status = "fail" if report.hard_gate_blocked or report.score_blocked else "pass"
            evidence.summary = {
                "score": report.final_score,
                "hard_gate_blocked": report.hard_gate_blocked,
                "score_blocked": report.score_blocked,
            }
            evidence.raw = _serialize_for_json(report)
        except Exception as error:  # noqa: BLE001
            evidence.status = "error"
            evidence.raw = {"error": str(error)}
        return _finish_evidence(evidence, started)


class EntrixReviewTriggerProducer(Producer):
    """Produce review-trigger evidence through the public review-trigger API."""

    def __init__(self, config: EvidenceProducerConfig, rules: list[ReviewTriggerRule]) -> None:
        self.config = config
        self.rules = rules

    def run(self, context: ProducerContext) -> Evidence:
        started = monotonic()
        evidence = _new_evidence(self.config, "entrix-review-trigger", context)
        try:
            from entrix.review_trigger import (
                collect_changed_files,
                collect_diff_stats,
                evaluate_review_triggers,
            )

            base = context.base_ref
            if context.deadline is None:
                changed_files = collect_changed_files(context.repo_root, base)
                diff_stats = collect_diff_stats(context.repo_root, base)
            else:
                changed_files = collect_changed_files(
                    context.repo_root, base, deadline=context.deadline
                )
                diff_stats = collect_diff_stats(
                    context.repo_root, base, deadline=context.deadline
                )
            report = evaluate_review_triggers(
                self.rules,
                changed_files,
                diff_stats,
                base=base,
                repo_root=context.repo_root,
            )
            evidence.status = "fail" if report.human_review_required else "pass"
            evidence.summary = {
                "human_review_required": report.human_review_required,
                "triggered_rules": [trigger.name for trigger in report.triggers],
            }
            evidence.raw = report.to_dict()
        except Exception as error:  # noqa: BLE001
            evidence.status = "error"
            evidence.raw = {"error": str(error)}
        return _finish_evidence(evidence, started)


class DiffStatsProducer(Producer):
    """Collect git diff statistics for the files selected by the harness context."""

    def __init__(self, config: EvidenceProducerConfig) -> None:
        self.config = config

    def run(self, context: ProducerContext) -> Evidence:
        started = monotonic()
        evidence = _new_evidence(self.config, "diff-stats", context)
        try:
            changed_files = context.when_context.changed_files or []
            total_added = 0
            total_deleted = 0
            for file_path in changed_files:
                timeout = None
                if context.deadline is not None:
                    timeout = context.deadline - monotonic()
                    if timeout <= 0:
                        raise subprocess.TimeoutExpired("git diff", timeout)
                result = subprocess.run(
                    ["git", "diff", "--numstat", context.base_ref, "--", file_path],
                    capture_output=True,
                    text=True,
                    cwd=context.repo_root,
                    check=False,
                    timeout=timeout,
                )
                if not result.stdout.strip():
                    continue
                parts = result.stdout.strip().split()
                if len(parts) < 2:
                    continue
                total_added += int(parts[0])
                total_deleted += int(parts[1])

            evidence.status = "pass"
            evidence.summary = {
                "added_lines": total_added,
                "deleted_lines": total_deleted,
                "changed_files": len(changed_files),
                "files": changed_files,
            }
        except Exception as error:  # noqa: BLE001
            evidence.status = "error"
            evidence.raw = {"error": str(error)}
        return _finish_evidence(evidence, started)
