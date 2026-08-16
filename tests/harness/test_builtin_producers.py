"""Builtin producer tests."""
import pytest
from pathlib import Path
from entrix.harness.producers.builtin import (
    EntrixFitnessProducer,
    EntrixReviewTriggerProducer,
    DiffStatsProducer,
)
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.producers.base import ProducerContext
from entrix.harness.conditions import WhenContext


def test_entrix_fitness_producer():
    """测试 EntrixFitnessProducer 生成 fitness 证据"""
    config = EvidenceProducerConfig(
        id="fitness",
        type="fitness",
        name="Entrix fitness 报告",
        builtin="entrix-fitness",
    )

    producer = EntrixFitnessProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd()),
    )

    evidence = producer.run(context)

    assert evidence.id == "fitness"
    assert evidence.type == "fitness"
    # Should contain fitness-specific fields or error status
    assert evidence.status in ["pass", "fail", "error"]


def test_entrix_review_trigger_producer():
    """测试 EntrixReviewTriggerProducer 生成审查触发证据"""
    config = EvidenceProducerConfig(
        id="review-trigger",
        type="review-trigger",
        name="审查触发评估",
        builtin="entrix-review-trigger",
    )

    producer = EntrixReviewTriggerProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd()),
    )

    evidence = producer.run(context)

    assert evidence.id == "review-trigger"
    assert evidence.type == "review-trigger"
    # Should contain human_review_required field or error status
    assert evidence.status in ["pass", "fail", "error"]


def test_diff_stats_producer():
    """测试 DiffStatsProducer 生成差异统计"""
    config = EvidenceProducerConfig(
        id="diff-stats",
        type="diff",
        name="Git 差异统计",
        builtin="diff-stats",
    )

    producer = DiffStatsProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd(), changed_files=["README.md"]),
    )

    evidence = producer.run(context)

    assert evidence.id == "diff-stats"
    assert evidence.type == "diff"
    # Should contain diff stats
    assert any(
        key in evidence.summary for key in ["added_lines", "deleted_lines", "changed_files"]
    )