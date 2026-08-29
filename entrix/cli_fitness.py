"""Fitness 运行子命令：harness run/validate、run、validate、review-trigger。

从 cli.py 拆出；状态/生命周期命令见 cli_lifecycle，graph 见 cli_graph。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

import entrix.cli_runtime as _cli_runtime
from entrix.engine import collect_changed_files, run_fitness_report
from entrix.gitinfo import find_project_root
from entrix.governance import GovernancePolicy, StreamOutputMode, enforce
from entrix.harness.config import HarnessConfig, find_harness_config, load_harness_config
from entrix.harness.fitness import validate_weights
from entrix.model import ExecutionScope, Gate, Metric, MetricResult, ResultState, Tier
from entrix.presets import get_project_preset
from entrix.reporters.terminal import TerminalReporter
from entrix.reporters.visual import AsciiReporter, RichLiveProgressReporter, RichReporter
from entrix.reporting import report_to_dict, write_report_output
from entrix.review_trigger import collect_changed_files as collect_review_changed_files
from entrix.review_trigger import collect_diff_stats, evaluate_review_triggers
from entrix.stop_gate.runner import HarnessRunner


class _ShellOutputController:
    """协调 progress 输出，支持可选的 shell 日志流模式。"""

    def __init__(self, reporter: TerminalReporter, *, mode: StreamOutputMode = "off"):
        self.reporter = reporter
        self.mode = mode
        self._buffered_lines: dict[int, list[tuple[str, str]]] = {}
        self._lock = RLock()

    @property
    def should_capture_output(self) -> bool:
        return self.mode != "off"

    def handle_output(self, metric: Metric, source: str, line: str) -> None:
        if self.mode == "off":
            return
        if self.mode == "all":
            with self._lock:
                self.reporter.print_metric_output(metric_name=metric.name, source=source, line=line)
            return
        with self._lock:
            self._buffered_lines.setdefault(id(metric), []).append((source, line))

    def handle_progress(self, event: str, metric: Metric, result: MetricResult | None) -> None:
        with self._lock:
            self.reporter.print_metric_progress(
                event,
                metric_name=metric.name,
                tier=metric.tier.value,
                hard_gate=metric.gate == Gate.HARD,
                result=result,
            )
        if event != "end" or self.mode != "failures":
            return
        buffered = self._pop_buffer(metric)
        if result is None or result.state != ResultState.FAIL:
            return
        for source, line in buffered:
            with self._lock:
                self.reporter.print_metric_output(metric_name=metric.name, source=source, line=line)

    def _pop_buffer(self, metric: Metric) -> list[tuple[str, str]]:
        with self._lock:
            return self._buffered_lines.pop(id(metric), [])


def _find_project_root() -> Path:
    """从 CWD 向上遍历查找项目根目录；实现共享于 entrix.gitinfo。"""

    return find_project_root()




def _runtime_root(project_root: Path) -> Path:
    """Compatibility seam for callers that isolate CLI runtime files in tests."""
    return _cli_runtime.runtime_root(project_root)


def cmd_harness_validate(args: argparse.Namespace) -> int:
    """验证harness.yaml配置。"""
    config_path = Path(args.config).resolve() if args.config else Path.cwd() / "harness.yaml"

    try:
        config = load_harness_config(config_path)
        print(f"有效的 harness 配置: {config_path}")
        print(f"  版本: {config.version}")
        print(f"  证据生产者: {len(config.evidence_producers)}")
        print(f"  门禁策略: {len(config.gate_policies)}")
        return 0
    except Exception as e:
        print(f"无效的配置: {e}", file=sys.stderr)
        return 1


def cmd_harness_run(args: argparse.Namespace) -> int:
    """执行harness收集和门禁裁决。"""
    repo_root = Path.cwd()
    config_path: Path | None
    if args.config:
        config_path = Path(args.config).resolve()
    else:
        config_path = _find_harness_config(repo_root)
        if config_path is None:
            print("未找到 harness.yaml 或 .harness/harness.yaml", file=sys.stderr)
            return 1

    try:
        runner = HarnessRunner(
            config_path,
            evidence_root=repo_root,
            parallel_producers=args.parallel,
            max_parallel_producers=args.max_workers if args.parallel else None,
        )
        result = runner.run(
            {
                "workspace": repo_root,
                "task_id": "manual-run",
                "changed_files": [],
                "branch": "manual",
                "base_ref": "HEAD",
            }
        )
        verdict = result.verdict
        bundle = result.bundle

        # 输出结果
        if args.json:
            output = {
                "status": verdict.status.value,
                "summary": verdict.summary,
                "evidence_count": len(bundle.evidence) if bundle else 0,
                "gate_results": [
                    {
                        "policy": gate_result.policy_name,
                        "severity": gate_result.severity.value,
                        "passed": gate_result.passed,
                        "active": gate_result.active,
                        "message": gate_result.message,
                    }
                    for gate_result in verdict.gate_results
                ],
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(f"\n{'=' * 50}")
            print(f"Verdict: {verdict.status.value.upper()}")
            print(f"{'=' * 50}")
            print(f"Summary: {verdict.summary}")
            if bundle is not None:
                print(f"已收集 {len(bundle.evidence)} 条证据", file=sys.stderr)

            if verdict.gate_results:
                print("\nGate results:")
                for gate_result in verdict.gate_results:
                    status_icon = "✓" if gate_result.passed else "✗"
                    print(
                        f"  {status_icon} {gate_result.policy_name} "
                        f"({gate_result.severity.value}): {gate_result.message}"
                    )

        # 返回适当的退出码
        return 0 if verdict.status.value == "pass" else 1

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1




def _find_harness_config(project_root: Path) -> Path | None:
    """查找项目根目录的 Harness 配置。"""
    from entrix.harness.config import find_harness_config as _find_config

    return _find_config(project_root)


def _load_project_harness(
    project_root: Path,
    config_path: Path | None = None,
) -> HarnessConfig:
    """加载项目 Harness 配置，供显式质量命令共享。"""
    selected_path = config_path or _find_harness_config(project_root)
    if selected_path is None:
        raise FileNotFoundError(f"未找到 Harness 配置：{project_root / 'harness.yaml'}")
    return load_harness_config(selected_path)


def _print_json(data: dict) -> None:
    from entrix.cli_runtime import print_json

    print_json(data)


def _print_review_trigger_report(report: dict) -> None:
    print("REVIEW TRIGGER REPORT")
    print(f"Base: {report['base']}")
    stats = report.get("diff_stats", {})
    print(
        "Diff stats: "
        f"files={stats.get('file_count', 0)} "
        f"added={stats.get('added_lines', 0)} "
        f"deleted={stats.get('deleted_lines', 0)}"
    )
    if report.get("human_review_required"):
        print("Human review required: yes")
        for trigger in report.get("triggers", []):
            print(f"- {trigger['name']} [{trigger['severity']}]")
            for reason in trigger.get("reasons", []):
                print(f"  reason: {reason}")
    else:
        print("Human review required: no")


def _domains_from_files(files: list[str]) -> set[str]:
    return get_project_preset().domains_from_files(files)


def _metric_domains(metric: Metric) -> set[str]:
    return get_project_preset().metric_domains(metric)


def _collect_run_files(args: argparse.Namespace, project_root: Path) -> list[str]:
    explicit_files = args.files or []
    if explicit_files:
        return explicit_files
    if args.changed_only:
        return collect_changed_files(project_root, args.base)
    return []


def cmd_run(args: argparse.Namespace) -> int:
    """将架构 fitness 函数作为可执行的 guardrail 检查运行。"""
    project_root = (
        Path(args.repo).resolve()
        if getattr(args, "repo", None)
        else _find_project_root()
    )
    try:
        harness_config = _load_project_harness(project_root)
    except (FileNotFoundError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    preset = get_project_preset()
    run_started_at = time.perf_counter()

    tier_filter = Tier(args.tier) if args.tier else None
    execution_scope = ExecutionScope(args.scope) if args.scope else ExecutionScope.LOCAL
    policy = GovernancePolicy(
        tier_filter=tier_filter,
        parallel=args.parallel,
        max_workers=getattr(args, "max_workers", 4),
        dry_run=args.dry_run,
        verbose=args.verbose,
        stream_output=args.stream,
        min_score=args.min_score,
        execution_scope=execution_scope,
        dimension_filters=tuple(args.dimension or ()),
        metric_filters=tuple(args.metric or ()),
    )

    output_format = getattr(args, "format", "text")
    reporter = TerminalReporter(verbose=policy.verbose)
    shell_output = _ShellOutputController(reporter, mode=policy.stream_output)
    live_reporter = (
        RichLiveProgressReporter(
            stream=sys.stdout,
            refresh_per_second=max(1, int(args.progress_refresh)),
        )
        if output_format == "rich" and sys.stdout.isatty() and not policy.dry_run
        else None
    )
    reporter.print_header(
        dry_run=policy.dry_run,
        tier=args.tier,
        parallel=policy.parallel,
    )

    changed_files = _collect_run_files(args, project_root)
    if args.changed_only or changed_files:
        if args.changed_only and not changed_files:
            print("No changed files detected; skipping fitness run.")
            write_report_output(
                args.output,
                {
                    "final_score": 0.0,
                    "hard_gate_blocked": False,
                    "score_blocked": False,
                    "dimensions": [],
                },
            )
            _cli_runtime.emit_runtime_fitness_event(
                project_root,
                status="skipped",
                tier=args.tier,
                report=None,
                metric_count=0,
                duration_ms=0.0,
                artifact_path=None,
                runtime_root_resolver=_runtime_root,
            )
            return 0

        changed_domains = preset.domains_from_files(changed_files)
        print(
            f"\nIncremental mode: base={args.base}, changed_files={len(changed_files)}, domains={','.join(sorted(changed_domains)) or 'none'}"
        )
    report, dimensions = run_fitness_report(
        project_root,
        policy,
        preset,
        dimensions=harness_config.fitness_dimensions,
        changed_files=changed_files or None,
        base=args.base,
        progress_setup_callback=(None if live_reporter is None else live_reporter.setup),
        progress_callback=(
            None
            if policy.dry_run
            else (
                live_reporter.handle_progress
                if live_reporter is not None
                else shell_output.handle_progress
            )
        ),
        shell_output_callback=(
            None
            if policy.dry_run or live_reporter is not None or output_format != "text" or not shell_output.should_capture_output
            else shell_output.handle_output
        ),
    )
    if live_reporter is not None:
        live_reporter.close()

    if not dimensions:
        print("No metrics matched the current run filters; skipping fitness run.")
        write_report_output(
            args.output,
            {
                "final_score": 0.0,
                "hard_gate_blocked": False,
                "score_blocked": False,
                "dimensions": [],
            },
        )
        _cli_runtime.emit_runtime_fitness_event(
            project_root,
            status="skipped",
            tier=args.tier,
            report=None,
            metric_count=0,
            duration_ms=0.0,
            artifact_path=None,
            runtime_root_resolver=_runtime_root,
        )
        return 0

    if output_format == "text":
        for dim, ds in zip(dimensions, report.dimensions, strict=True):
            print(f"\n## {dim.name.upper()} (weight: {dim.weight}%)")
            print(f"   Source: {dim.source_file}")

            for result in ds.results:
                state_labels: dict[ResultState | None, str] = {
                    ResultState.PASS: "\u2705 PASS",
                    ResultState.FAIL: "\u274c FAIL",
                    ResultState.UNKNOWN: "\u2753 UNKNOWN",
                    ResultState.SKIPPED: "\u23ed\ufe0f SKIPPED",
                    ResultState.WAIVED: "\u26a0\ufe0f WAIVED",
                }
                status = state_labels.get(result.state, "\u2753 UNKNOWN")
                hard = " [HARD GATE]" if result.hard_gate else ""
                tier_label = f" [{result.tier.value}]" if tier_filter else ""
                print(f"   - {result.metric_name}: {status}{hard}{tier_label}")

                if result.state == ResultState.FAIL and (policy.verbose or result.hard_gate):
                    if result.output:
                        lines = result.output.strip().split("\n")
                        for line in lines[:10]:
                            print(f"     > {line}")
                        if len(lines) > 10:
                            print(f"     > ... ({len(lines) - 10} more lines)")

            if ds.total > 0:
                print(f"   Score: {ds.score:.0f}%")

        reporter.print_footer(report)
    elif output_format == "ascii":
        AsciiReporter().report(report)
    else:
        RichReporter().report(report)

    write_report_output(args.output, report_to_dict(report))
    exit_code = enforce(report, policy)
    duration_ms = (time.perf_counter() - run_started_at) * 1000.0
    observed_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    artifact_path = str(
        _cli_runtime.fitness_artifact_path(
            project_root, tier=args.tier, observed_at_ms=observed_at_ms
        )
    )
    snapshot = _cli_runtime.build_runtime_fitness_snapshot(
        project_root,
        tier=args.tier,
        report=report,
        duration_ms=duration_ms,
        artifact_path=artifact_path,
        observed_at_ms=observed_at_ms,
        producer="entrix",
        base_ref=(args.base if changed_files else None),
        changed_files=changed_files,
    )
    artifact_path = _cli_runtime.write_runtime_fitness_artifacts(
        project_root,
        tier=args.tier,
        snapshot=snapshot,
        observed_at_ms=observed_at_ms,
        runtime_root_resolver=_runtime_root,
    )
    _cli_runtime.emit_runtime_fitness_event(
        project_root,
        status="passed" if exit_code == 0 else "failed",
        tier=args.tier,
        report=report,
        metric_count=sum(len(ds.results) for ds in report.dimensions),
        duration_ms=duration_ms,
        artifact_path=artifact_path,
        runtime_root_resolver=_runtime_root,
    )
    return exit_code


def cmd_validate(args: argparse.Namespace) -> int:
    """验证 dimension 权重之和为 100%。"""
    project_root = _find_project_root()
    try:
        config = _load_project_harness(project_root)
    except (FileNotFoundError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    dimensions = config.fitness_dimensions
    valid, total = validate_weights(dimensions)

    for dim in dimensions:
        print(f"  {dim.name}: {dim.weight}%  ({dim.source_file})")

    print(f"\nTotal: {total}%")
    if valid:
        print("\u2705 Weights sum to 100%")
        return 0

    print(f"\u274c Weights sum to {total}%, expected 100%")
    return 1


def cmd_review_trigger(args: argparse.Namespace) -> int:
    """针对当前 diff 评估 review-trigger 规则。"""
    project_root = _find_project_root()
    try:
        config = _load_project_harness(
            project_root,
            Path(args.config).resolve() if args.config else None,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    rules = config.review_trigger_rules
    changed_files = args.files or collect_review_changed_files(project_root, args.base)
    diff_stats = collect_diff_stats(project_root, args.base)
    report = evaluate_review_triggers(
        rules,
        changed_files,
        diff_stats,
        base=args.base,
        repo_root=project_root,
    )

    if args.json:
        _print_json(report.to_dict())
    else:
        _print_review_trigger_report(report.to_dict())

    if report.human_review_required and args.fail_on_trigger:
        return 3
    return 0
