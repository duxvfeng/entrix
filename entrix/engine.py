"""fitness run 的共享执行引擎。"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Callable

from entrix.governance import GovernancePolicy, filter_dimensions
from entrix.loaders import load_dimensions
from entrix.model import Dimension, EvidenceType, FitnessReport, Gate, Metric, MetricResult, ResultState
from entrix.presets.base import ProjectPreset
from entrix.runners.graph import GraphRunner
from entrix.runners.sarif import SarifRunner
from entrix.runners.shell import OutputCallback
from entrix.runners.shell import ShellRunner
from entrix.scoring import score_dimension, score_report

ProgressCallback = Callable[[str, Metric, MetricResult | None], None]
ProgressSetupCallback = Callable[[list[Dimension]], None]


def collect_changed_files(project_root: Path, base: str) -> list[str]:
    """为增量 fitness run 从 git 收集变更文件。

    只包含已提交（相对于 base 领先）或已暂存的文件。
    未跟踪和未暂存的工作区改动被排除，避免无关的 WIP 污染 fitness 范围。
    """
    from entrix.presets import get_project_preset

    preset = get_project_preset()
    files: list[str] = []

    commands = [
        # 相对于 base 的已提交改动
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base],
        # 暂存区（index）的改动
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"],
    ]

    for command in commands:
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        files.extend(line.strip() for line in result.stdout.splitlines() if line.strip())

    seen: set[str] = set()
    deduped: list[str] = []
    for file_path in files:
        if preset.should_ignore_changed_file(file_path):
            continue
        if file_path not in seen:
            seen.add(file_path)
            deduped.append(file_path)
    return deduped


def matches_changed_files(
    metric: Metric,
    changed_files: list[str],
    domains: set[str],
    preset: ProjectPreset,
) -> bool:
    """检查某个 metric 是否应该对变更文件集运行。"""
    if metric.run_when_changed:
        return any(
            fnmatch.fnmatch(changed_file, pattern)
            for changed_file in changed_files
            for pattern in metric.run_when_changed
        )
    if not domains:
        return False
    if "config" in domains:
        return True
    metric_domains = preset.metric_domains(metric)
    return "global" in metric_domains or bool(metric_domains.intersection(domains))


def filter_dimensions_for_incremental(
    dimensions: list[Dimension],
    changed_files: list[str],
    domains: set[str],
    preset: ProjectPreset,
) -> list[Dimension]:
    """只返回包含与变更文件集相关 metric 的 dimension。"""
    if not changed_files:
        return []
    if "config" in domains:
        return dimensions

    filtered_dimensions: list[Dimension] = []
    for dimension in dimensions:
        filtered_metrics = []
        for metric in dimension.metrics:
            if matches_changed_files(metric, changed_files, domains, preset):
                filtered_metrics.append(metric)
        if filtered_metrics:
            filtered_dimensions.append(
                Dimension(
                    name=dimension.name,
                    weight=dimension.weight,
                    threshold_pass=dimension.threshold_pass,
                    threshold_warn=dimension.threshold_warn,
                    metrics=filtered_metrics,
                    source_file=dimension.source_file,
                )
            )
    return filtered_dimensions


def run_fitness_report(
    project_root: Path,
    policy: GovernancePolicy,
    preset: ProjectPreset,
    *,
    changed_files: list[str] | None = None,
    base: str = "HEAD",
    progress_callback: ProgressCallback | None = None,
    progress_setup_callback: ProgressSetupCallback | None = None,
    shell_output_callback: OutputCallback | None = None,
) -> tuple[FitnessReport, list[Dimension]]:
    """执行一次 fitness run，返回报告以及选中的 dimension。"""
    dimensions = filter_dimensions(load_dimensions(preset.fitness_dir(project_root)), policy)

    runner_env: dict[str, str] = {}
    effective_changed_files = changed_files or []
    if effective_changed_files:
        changed_domains = preset.domains_from_files(effective_changed_files)
        dimensions = filter_dimensions_for_incremental(
            dimensions,
            effective_changed_files,
            changed_domains,
            preset,
        )
        runner_env = {
            "ROUTA_FITNESS_CHANGED_ONLY": "1",
            "ROUTA_FITNESS_CHANGED_BASE": base,
            "ROUTA_FITNESS_CHANGED_FILES": "\n".join(effective_changed_files),
        }

    if progress_setup_callback is not None:
        progress_setup_callback(dimensions)

    shell_runner = ShellRunner(
        project_root,
        env_overrides=runner_env,
        stream_output=policy.stream_output != "off",
        output_callback=shell_output_callback,
    )
    sarif_runner = SarifRunner(project_root, env_overrides=runner_env)
    graph_runner = GraphRunner(project_root)
    dimension_scores = []
    for dim in dimensions:
        results = _run_metric_batch(
            dim.metrics,
            shell_runner=shell_runner,
            sarif_runner=sarif_runner,
            graph_runner=graph_runner,
            dry_run=policy.dry_run,
            parallel=policy.parallel,
            changed_files=effective_changed_files,
            base=base,
            progress_callback=progress_callback,
        )
        dimension_scores.append(score_dimension(results, dim.name, dim.weight))

    return score_report(dimension_scores, min_score=policy.min_score), dimensions


def _run_metric_batch(
    metrics: list[Metric],
    *,
    shell_runner: ShellRunner,
    sarif_runner: SarifRunner,
    graph_runner: GraphRunner,
    dry_run: bool,
    parallel: bool,
    changed_files: list[str],
    base: str,
    progress_callback: ProgressCallback | None,
) -> list[MetricResult]:
    """执行混合的 shell 和 probe metric 批次，同时保持顺序。"""
    results: list[MetricResult] = []
    shell_batch: list[Metric] = []
    shell_indexes: list[int] = []
    sarif_batch: list[Metric] = []
    sarif_indexes: list[int] = []

    for index, metric in enumerate(metrics):
        if metric.evidence_type == EvidenceType.PROBE:
            results.append(
                _run_probe_metric(
                    metric,
                    graph_runner=graph_runner,
                    dry_run=dry_run,
                    changed_files=changed_files,
                    base=base,
                    progress_callback=progress_callback,
                )
            )
            continue
        if metric.evidence_type == EvidenceType.SARIF:
            results.append(
                MetricResult(
                    metric_name=metric.name,
                    passed=False,
                    output="",
                    tier=metric.tier,
                    hard_gate=metric.gate == Gate.HARD,
                    state=ResultState.UNKNOWN,
                )
            )
            sarif_batch.append(metric)
            sarif_indexes.append(index)
            continue

        results.append(
            MetricResult(
                metric_name=metric.name,
                passed=False,
                output="",
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
                state=ResultState.UNKNOWN,
            )
        )
        shell_batch.append(metric)
        shell_indexes.append(index)

    if shell_batch:
        shell_results = shell_runner.run_batch(
            shell_batch,
            parallel=parallel,
            dry_run=dry_run,
            progress_callback=progress_callback,
        )
        for index, result in zip(shell_indexes, shell_results, strict=False):
            results[index] = result

    if sarif_batch:
        for metric in sarif_batch:
            _emit_progress(progress_callback, "start", metric)
        sarif_results = sarif_runner.run_batch(
            sarif_batch,
            dry_run=dry_run,
        )
        for metric, index, result in zip(sarif_batch, sarif_indexes, sarif_results, strict=False):
            _emit_progress(progress_callback, "end", metric, result)
            results[index] = result

    return results


def _run_probe_metric(
    metric: Metric,
    *,
    graph_runner: GraphRunner,
    dry_run: bool,
    changed_files: list[str],
    base: str,
    progress_callback: ProgressCallback | None,
) -> MetricResult:
    """执行基于代码图的 probe metric。"""
    _emit_progress(progress_callback, "start", metric)
    if metric.waiver and metric.waiver.is_active():
        result = MetricResult(
            metric_name=metric.name,
            passed=True,
            output=f"[WAIVED] {metric.waiver.reason}",
            tier=metric.tier,
            hard_gate=metric.gate == Gate.HARD,
            state=ResultState.WAIVED,
        )
        _emit_progress(progress_callback, "end", metric, result)
        return result

    if dry_run:
        result = MetricResult(
            metric_name=metric.name,
            passed=True,
            output=f"[DRY-RUN] Would run probe: {metric.command}",
            tier=metric.tier,
            hard_gate=metric.gate == Gate.HARD,
        )
        _emit_progress(progress_callback, "end", metric, result)
        return result

    if metric.command == "graph:impact":
        result = graph_runner.probe_impact(changed_files or None, base=base)
    elif metric.command in {"graph:test-radius", "graph:test-coverage"}:
        result = graph_runner.probe_test_coverage(changed_files or None, base=base)
    elif metric.command == "graph:test-mapping":
        result = graph_runner.probe_test_mapping(changed_files or None, base=base)
    else:
        result = MetricResult(
            metric_name=metric.name,
            passed=False,
            output=f"Unsupported probe command: {metric.command}",
            tier=metric.tier,
            hard_gate=metric.gate == Gate.HARD,
            state=ResultState.UNKNOWN,
        )
        _emit_progress(progress_callback, "end", metric, result)
        return result

    result.metric_name = metric.name
    result.tier = metric.tier
    result.hard_gate = metric.gate == Gate.HARD
    _emit_progress(progress_callback, "end", metric, result)
    return result


def _emit_progress(
    callback: ProgressCallback | None,
    event: str,
    metric: Metric,
    result: MetricResult | None = None,
) -> None:
    if callback is not None:
        callback(event, metric, result)
