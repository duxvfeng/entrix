"""Builtin producer tests."""
import entrix.harness.producers.builtin as builtin_module
from entrix.harness.conditions import WhenContext
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.producers.base import ProducerContext
from entrix.harness.producers.builtin import (
    DiffStatsProducer,
    EntrixFitnessProducer,
    EntrixReviewTriggerProducer,
)
from entrix.model import Dimension, FitnessReport, Metric
from entrix.review_trigger import DiffStats, ReviewTriggerReport, ReviewTriggerRule, TriggerMatch


def test_fitness_producer_uses_injected_dimensions(monkeypatch, tmp_path):
    """Fitness producer passes Harness dimensions to the shared engine."""
    config = EvidenceProducerConfig(
        id="fitness",
        type="fitness",
        name="Entrix fitness 报告",
        builtin="entrix-fitness",
    )
    dimensions = [Dimension(name="quality", weight=100, metrics=[Metric(name="lint", command="true")])]
    producer = EntrixFitnessProducer(config, dimensions)
    calls = {}

    def fake_run_fitness_report(project_root, policy, preset, **kwargs):
        calls["dimensions"] = kwargs["dimensions"]
        return FitnessReport(final_score=91.0), dimensions

    monkeypatch.setattr("entrix.engine.run_fitness_report", fake_run_fitness_report)

    context = ProducerContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
    )

    evidence = producer.run(context)

    assert evidence.status == "pass"
    assert calls["dimensions"] == dimensions


def test_review_trigger_producer_uses_injected_rules(monkeypatch, tmp_path):
    """Review producer evaluates rules supplied by HarnessConfig."""
    config = EvidenceProducerConfig(
        id="review-trigger",
        type="review-trigger",
        name="审查触发评估",
        builtin="entrix-review-trigger",
    )
    rules = [ReviewTriggerRule(name="sensitive", type="sensitive_file_change")]
    producer = EntrixReviewTriggerProducer(config, rules)
    calls = {}

    monkeypatch.setattr(
        "entrix.review_trigger.collect_changed_files",
        lambda _repo_root, _base: [],
    )
    monkeypatch.setattr(
        "entrix.review_trigger.collect_diff_stats",
        lambda _repo_root, _base: DiffStats(),
    )

    def fake_evaluate_review_triggers(rules_arg, changed_files, diff_stats, *, base, repo_root):
        calls["rules"] = rules_arg
        return ReviewTriggerReport(human_review_required=False, base=base)

    monkeypatch.setattr("entrix.review_trigger.evaluate_review_triggers", fake_evaluate_review_triggers)

    context = ProducerContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
    )

    evidence = producer.run(context)

    assert evidence.status == "pass"
    assert calls["rules"] == rules


def test_entrix_fitness_producer(monkeypatch, tmp_path):
    """测试 EntrixFitnessProducer 生成 fitness 证据"""
    config = EvidenceProducerConfig(
        id="fitness",
        type="fitness",
        name="Entrix fitness 报告",
        builtin="entrix-fitness",
    )

    producer = EntrixFitnessProducer(config, [])
    calls = {}

    def fake_run_fitness_report(project_root, policy, preset, **kwargs):
        calls["args"] = (project_root, policy, preset, kwargs)
        return FitnessReport(final_score=91.0), []

    monkeypatch.setattr("entrix.engine.run_fitness_report", fake_run_fitness_report)

    context = ProducerContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path, changed_files=["entrix/engine.py"]),
        base_ref="origin/main",
    )

    evidence = producer.run(context)

    assert evidence.id == "fitness"
    assert evidence.type == "fitness"
    assert evidence.status == "pass"
    assert evidence.summary == {
        "score": 91.0,
        "hard_gate_blocked": False,
        "score_blocked": False,
    }
    assert calls["args"][0] == tmp_path
    assert calls["args"][3]["changed_files"] == ["entrix/engine.py"]
    assert calls["args"][3]["base"] == "origin/main"


def test_entrix_review_trigger_producer(monkeypatch, tmp_path):
    """测试 EntrixReviewTriggerProducer 生成审查触发证据"""
    config = EvidenceProducerConfig(
        id="review-trigger",
        type="review-trigger",
        name="审查触发评估",
        builtin="entrix-review-trigger",
    )

    rules = [ReviewTriggerRule(name="sensitive", type="sensitive_file_change")]
    producer = EntrixReviewTriggerProducer(config, rules)
    calls = {}

    def fake_collect_changed_files(repo_root, base):
        calls["changed_files"] = (repo_root, base)
        return ["entrix/model.py"]

    def fake_collect_diff_stats(repo_root, base):
        calls["diff_stats"] = (repo_root, base)
        return DiffStats(file_count=1, added_lines=4, deleted_lines=1)

    def fake_evaluate_review_triggers(rules, changed_files, diff_stats, *, base, repo_root):
        calls["evaluate"] = (rules, changed_files, diff_stats, base, repo_root)
        return ReviewTriggerReport(
            human_review_required=True,
            base=base,
            changed_files=tuple(changed_files),
            diff_stats=diff_stats,
            triggers=(TriggerMatch(name="sensitive", severity="high", action="require_human_review"),),
        )

    monkeypatch.setattr("entrix.review_trigger.collect_changed_files", fake_collect_changed_files)
    monkeypatch.setattr("entrix.review_trigger.collect_diff_stats", fake_collect_diff_stats)
    monkeypatch.setattr("entrix.review_trigger.evaluate_review_triggers", fake_evaluate_review_triggers)

    context = ProducerContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
        base_ref="origin/main",
    )

    evidence = producer.run(context)

    assert evidence.id == "review-trigger"
    assert evidence.type == "review-trigger"
    assert evidence.status == "fail"
    assert evidence.summary["human_review_required"] is True
    assert evidence.summary["triggered_rules"] == ["sensitive"]
    assert calls["evaluate"][0] == rules
    assert calls["changed_files"] == (tmp_path, "origin/main")
    assert calls["diff_stats"] == (tmp_path, "origin/main")
    assert calls["evaluate"][3] == "origin/main"


def test_diff_stats_producer_uses_context_base_ref(monkeypatch, tmp_path):
    """测试 DiffStatsProducer 生成差异统计"""
    config = EvidenceProducerConfig(
        id="diff-stats",
        type="diff",
        name="Git 差异统计",
        builtin="diff-stats",
    )

    producer = DiffStatsProducer(config)
    commands = []
    ticks = iter([10.0, 10.125])
    monkeypatch.setattr(builtin_module, "monotonic", lambda: next(ticks), raising=False)

    class Result:
        stdout = "3\t1\tREADME.md\n"

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return Result()

    monkeypatch.setattr("entrix.harness.producers.builtin.subprocess.run", fake_run)
    context = ProducerContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path, changed_files=["README.md"]),
        base_ref="origin/main",
    )

    evidence = producer.run(context)

    assert evidence.id == "diff-stats"
    assert evidence.type == "diff"
    assert evidence.duration_ms == 125
    # Should contain diff stats
    assert any(
        key in evidence.summary for key in ["added_lines", "deleted_lines", "changed_files"]
    )
    assert commands[0][0] == ["git", "diff", "--numstat", "origin/main", "--", "README.md"]
