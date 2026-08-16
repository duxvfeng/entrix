"""Builtin evidence producers for Entrix-specific functionality."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from entrix.harness.producers.base import Producer, ProducerContext
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.evidence import Evidence


class EntrixFitnessProducer(Producer):
    """Producer that runs Entrix fitness report."""

    def __init__(self, config: EvidenceProducerConfig) -> None:
        self.config = config

    def run(self, context: ProducerContext) -> Evidence:
        """Execute fitness report and return evidence.

        Args:
            context: Execution context

        Returns:
            Evidence containing fitness results
        """
        evidence = Evidence(
            id=self.config.id,
            type=self.config.type,
            name=self.config.name,
            producer="entrix-fitness",
            task_id=context.task_id,
            started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        try:
            # Try to call existing fitness report functionality
            # This should integrate with existing entrix.fitness module
            from entrix.fitness import run_fitness_report

            fitness_result = run_fitness_report(context.repo_root)

            evidence.status = (
                "pass" if fitness_result.get("overall_status") == "pass" else "fail"
            )
            evidence.summary = {
                "score": fitness_result.get("score", 0),
                "hard_gate_blocked": fitness_result.get("hard_gate_blocked", False),
                "score_blocked": fitness_result.get("score_blocked", False),
            }
            evidence.raw = fitness_result

        except ImportError:
            # Fallback if fitness module is not available
            evidence.status = "error"
            evidence.raw = {"error": "Fitness module not available"}
        except Exception as e:
            evidence.status = "error"
            evidence.raw = {"error": str(e)}

        return evidence


class EntrixReviewTriggerProducer(Producer):
    """Producer that evaluates review triggers."""

    def __init__(self, config: EvidenceProducerConfig) -> None:
        self.config = config

    def run(self, context: ProducerContext) -> Evidence:
        """Evaluate review triggers and return evidence.

        Args:
            context: Execution context

        Returns:
            Evidence containing review trigger results
        """
        evidence = Evidence(
            id=self.config.id,
            type=self.config.type,
            name=self.config.name,
            producer="entrix-review-trigger",
            task_id=context.task_id,
            started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        try:
            # Try to call existing review trigger functionality
            from entrix.review_triggers import evaluate_review_triggers

            trigger_result = evaluate_review_triggers(context.repo_root)

            evidence.status = (
                "pass" if not trigger_result.get("human_review_required") else "fail"
            )
            evidence.summary = {
                "human_review_required": trigger_result.get("human_review_required", False),
                "triggered_rules": trigger_result.get("triggered_rules", []),
            }
            evidence.raw = trigger_result

        except ImportError:
            # Fallback if review triggers module is not available
            evidence.status = "error"
            evidence.raw = {"error": "Review triggers module not available"}
        except Exception as e:
            evidence.status = "error"
            evidence.raw = {"error": str(e)}

        return evidence


class DiffStatsProducer(Producer):
    """Producer that collects git diff statistics."""

    def __init__(self, config: EvidenceProducerConfig) -> None:
        self.config = config

    def run(self, context: ProducerContext) -> Evidence:
        """Collect diff statistics and return evidence.

        Args:
            context: Execution context

        Returns:
            Evidence containing diff statistics
        """
        evidence = Evidence(
            id=self.config.id,
            type=self.config.type,
            name=self.config.name,
            producer="diff-stats",
            task_id=context.task_id,
            started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        try:
            # Use changed files from context
            changed_files = context.when_context.changed_files or []

            # Calculate basic diff statistics
            total_added = 0
            total_deleted = 0

            for file_path in changed_files:
                try:
                    # Get diff for each file
                    result = subprocess.run(
                        ["git", "diff", "--numstat", "--", file_path],
                        capture_output=True,
                        text=True,
                        cwd=context.repo_root,
                    )

                    if result.stdout.strip():
                        parts = result.stdout.strip().split()
                        if len(parts) >= 2:
                            added = int(parts[0])
                            deleted = int(parts[1])
                            total_added += added
                            total_deleted += deleted
                except (subprocess.SubprocessError, ValueError):
                    continue

            evidence.status = "pass"
            evidence.summary = {
                "added_lines": total_added,
                "deleted_lines": total_deleted,
                "changed_files": len(changed_files),
                "files": changed_files,
            }

        except Exception as e:
            evidence.status = "error"
            evidence.raw = {"error": str(e)}

        return evidence