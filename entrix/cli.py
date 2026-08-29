"""CLI 入口：装配各子命令模块的参数解析器并提供 main 入口。

子命令处理逻辑按域拆分：fitness 见 cli_fitness，生命周期与运维见
cli_lifecycle，graph 见 cli_graph，长文件/钩子分析见 cli_analysis，
release-trigger 见 cli_release。
"""

from __future__ import annotations

import argparse
import sys

from entrix import __version__ as PACKAGE_VERSION
from entrix.cli_analysis import cmd_analyze_long_file, cmd_hook_file_length
from entrix.cli_fitness import (
    _domains_from_files,
    _metric_domains,
    _ShellOutputController,
    cmd_harness_run,
    cmd_harness_validate,
    cmd_review_trigger,
    cmd_run,
    cmd_validate,
)
from entrix.cli_graph import (
    cmd_graph_build,
    cmd_graph_history,
    cmd_graph_impact,
    cmd_graph_query,
    cmd_graph_review_context,
    cmd_graph_stats,
    cmd_graph_test_mapping,
    cmd_graph_test_radius,
)
from entrix.cli_hints import (
    HintingArgumentParser,
    print_next_steps,
    should_show_next_steps,
)
from entrix.cli_lifecycle import (
    _default_mcp_config,
    cmd_doctor,
    cmd_init,
    cmd_install,
    cmd_phase,
    cmd_serve,
    cmd_status,
    cmd_stop_gate,
    cmd_stop_gate_retry,
    cmd_trust,
)
from entrix.cli_overview import print_command_overview, show_subgroup_help
from entrix.cli_release import cmd_release_trigger
from entrix.harness.profiles import PROFILE_NAMES


def _configure_utf8_streams() -> None:
    """Keep CLI status output encodable when launched from Windows subprocesses."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except OSError:
                continue


def _positive_int(value: str) -> int:
    """Parse a strictly positive command-line integer."""
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _set_command_group_help(
    parser: HintingArgumentParser, command_path: tuple[str, ...]
) -> None:
    parser.command_path = ("entrix", *command_path)
    parser.set_defaults(_help_parser=parser)


def _command_path(args: argparse.Namespace) -> tuple[str, ...]:
    command = getattr(args, "command", None)
    if not command:
        return ()
    nested_commands = {
        "harness": "harness_command",
        "hook": "hook_command",
        "analyze": "analyze_command",
        "graph": "graph_command",
    }
    nested = getattr(args, nested_commands.get(command, ""), None)
    return (command, nested) if nested else (command,)


def build_parser() -> HintingArgumentParser:
    parser = HintingArgumentParser(
        prog="entrix",
        description="Entrix 可执行质量门禁",
        epilog=(
            "常用命令：\n"
            "  entrix init                 初始化 .mcp.json 与 harness.yaml\n"
            "  entrix phase planning      标记当前回合为规划阶段\n"
            "  entrix status              查看当前配置、阶段和门禁缓存\n"
            "  entrix doctor              检查插件运行环境和信任状态\n"
            "  entrix trust               确认 Harness 配置允许自动执行\n"
            "  entrix harness validate     检查 Harness 配置\n"
            "  entrix run                  执行 Fitness 指标\n"
            "  entrix harness run --json   收集 evidence 并执行门禁裁决\n"
            "  entrix review-trigger       识别需要人工审查的改动\n"
            "  entrix stop-gate            作为 Claude Code Stop Hook 执行\n"
            "  entrix serve                启动 MCP 服务\n"
            "\n"
            "命令提示：/entrix [init] [phase planning|implementation] "
            "[harness validate|run] [run] [stop-gate] [--repo <path>]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {PACKAGE_VERSION}",
        help="显示 Entrix 版本",
    )
    _set_command_group_help(parser, ())
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run guardrail checks")
    run_parser.add_argument(
        "--repo",
        default=None,
        help="项目根目录（默认从当前目录向上探测）",
    )
    run_parser.add_argument(
        "--tier", choices=["fast", "normal", "deep"], help="Run only metrics up to this tier"
    )
    run_parser.add_argument("--parallel", action="store_true", help="Run metrics in parallel")
    run_parser.add_argument(
        "--max-workers",
        type=_positive_int,
        default=4,
        help="Maximum concurrently running metrics when --parallel is set",
    )
    run_parser.add_argument("--dry-run", action="store_true", help="Show what would run")
    run_parser.add_argument("--verbose", action="store_true", help="Show output on failure")
    run_parser.add_argument(
        "--stream",
        nargs="?",
        choices=["off", "failures", "all"],
        const="all",
        default="failures",
        help="Stream shell metric stdout/stderr. Default: 'failures' (replay on fail). Use 'all' for live output, 'off' to suppress.",
    )
    run_parser.add_argument(
        "--format",
        choices=["text", "ascii", "rich"],
        default="text",
        help="Render final report as plain text, ASCII scorecard, or rich scorecard",
    )
    run_parser.add_argument(
        "--progress-refresh",
        type=int,
        default=4,
        help="Refresh rate for rich live progress updates",
    )
    run_parser.add_argument(
        "--min-score",
        type=float,
        default=80.0,
        help="Minimum weighted score before the run exits non-zero",
    )
    run_parser.add_argument(
        "--scope",
        choices=["local", "ci", "staging", "prod_observation"],
        help="Run only metrics for the given execution scope",
    )
    run_parser.add_argument(
        "--output",
        help="Write JSON report to a file path, or '-' for stdout",
    )
    run_parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Run only metrics relevant to changed files",
    )
    run_parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Explicit changed files used for incremental metric selection",
    )
    run_parser.add_argument(
        "--base",
        default="HEAD",
        help="Git base reference used by --changed-only",
    )
    run_parser.add_argument(
        "--dimension",
        action="append",
        default=[],
        help="Restrict execution to a dimension name; repeat to include multiple dimensions",
    )
    run_parser.add_argument(
        "--metric",
        action="append",
        default=[],
        help="Restrict execution to a metric name; repeat to include multiple metrics",
    )
    run_parser.set_defaults(func=cmd_run)

    install_parser = subparsers.add_parser(
        "install",
        help="Generate `.mcp.json` for Claude Code MCP integration",
    )
    install_parser.add_argument(
        "--repo",
        default=None,
        help="Optional repo root (defaults to current working directory).",
    )
    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print `.mcp.json` content without writing it.",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="明确替换已有的 entrix MCP 配置；其他 MCP server 始终保留。",
    )
    install_parser.set_defaults(func=cmd_install)

    init_parser = subparsers.add_parser("init", help="初始化 Harness（独立模式可合并 .mcp.json）")
    init_parser.add_argument(
        "--repo",
        default=None,
        help="Optional repo root (defaults to current working directory).",
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览 .mcp.json 与 harness.yaml，不写入文件。",
    )
    init_parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="auto",
        help="Harness 模板 profile；默认 auto，检测冲突时请显式选择。",
    )
    init_parser.add_argument("--force", action="store_true", help="覆盖已有 harness.yaml 并重建默认配置。")
    init_parser.set_defaults(func=cmd_init)

    phase_parser = subparsers.add_parser(
        "phase",
        help="设置当前 Stop Gate 阶段而不运行检查",
    )
    phase_parser.add_argument(
        "mode",
        choices=["planning", "implementation", "clear"],
        help="当前任务阶段",
    )
    phase_parser.add_argument(
        "--repo",
        default=None,
        help="Optional repo root (defaults to current working directory).",
    )
    phase_parser.add_argument(
        "--session-id",
        default=None,
        help="可选 Claude session id；提供后 phase 状态只对该 session 生效。",
    )
    phase_parser.set_defaults(func=cmd_phase)

    status_parser = subparsers.add_parser(
        "status",
        help="查看当前工作区、Harness、Phase 和 Stop Gate 缓存状态",
    )
    status_parser.add_argument("--repo", default=None, help="仓库根目录（默认自动探测）")
    status_parser.add_argument(
        "--session-id",
        default=None,
        help="Claude session id；默认使用 unknown-session",
    )
    status_parser.add_argument("--json", action="store_true", help="输出 JSON")
    status_parser.set_defaults(func=cmd_status)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="检查版本、Harness、信任、MCP 和插件运行时",
    )
    doctor_parser.add_argument("--repo", default=None, help="仓库根目录（默认自动探测）")
    doctor_parser.add_argument("--json", action="store_true", help="输出 JSON")
    doctor_parser.set_defaults(func=cmd_doctor)

    trust_parser = subparsers.add_parser(
        "trust",
        help="确认当前 Harness 配置允许 Stop Hook 自动执行其中的命令",
    )
    trust_parser.add_argument(
        "--repo",
        default=None,
        help="仓库根目录（默认当前目录）",
    )
    trust_parser.set_defaults(func=cmd_trust)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run Entrix MCP server over stdio.",
    )
    serve_parser.set_defaults(func=cmd_serve)

    stop_gate_parser = subparsers.add_parser(
        "stop-gate",
        help="Run the quality gate as a Claude Code Stop hook (reads hook payload from stdin)",
    )
    stop_gate_parser.add_argument(
        "action",
        nargs="?",
        choices=["retry"],
        help="retry 清理当前 session 的缓存裁决后重新运行",
    )
    stop_gate_parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Evidence collection timeout in seconds (env: ENTRIX_STOP_GATE_TIMEOUT).",
    )
    stop_gate_parser.add_argument(
        "--base",
        default=None,
        help="Optional git base ref for diff-based checks.",
    )
    stop_gate_parser.add_argument("--repo", default=None, help="retry 使用的仓库根目录")
    stop_gate_parser.add_argument("--session-id", default=None, help="retry 要清理的 Claude session id")
    stop_gate_parser.set_defaults(func=cmd_stop_gate)

    validate_parser = subparsers.add_parser("validate", help="Check dimension weights sum to 100%%")
    validate_parser.set_defaults(func=cmd_validate)

    review_trigger_parser = subparsers.add_parser(
        "review-trigger",
        help="Detect risky changes that should trigger human review",
    )
    review_trigger_parser.add_argument("files", nargs="*", help="Optional explicit changed files")
    review_trigger_parser.add_argument("--base", default="HEAD~1", help="Git diff base")
    review_trigger_parser.add_argument("--config", help="Optional review-trigger YAML config path")
    review_trigger_parser.add_argument(
        "--fail-on-trigger",
        action="store_true",
        help="Return non-zero when human review is required",
    )
    review_trigger_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    review_trigger_parser.set_defaults(func=cmd_review_trigger)

    release_trigger_parser = subparsers.add_parser(
        "release-trigger",
        help="Detect risky release-surface drift before publish",
    )
    release_trigger_parser.add_argument("files", nargs="*", help="Optional explicit changed files")
    release_trigger_parser.add_argument("--manifest", required=True, help="Release manifest JSON path")
    release_trigger_parser.add_argument("--baseline-manifest", help="Optional baseline manifest JSON path")
    release_trigger_parser.add_argument("--base", default="HEAD~1", help="Git diff base")
    release_trigger_parser.add_argument("--config", help="Optional release-trigger YAML config path")
    release_trigger_parser.add_argument(
        "--fail-on-trigger",
        action="store_true",
        help="Return non-zero when release review or block is required",
    )
    release_trigger_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    release_trigger_parser.set_defaults(func=cmd_release_trigger)

    # Harness system commands
    harness_parser = subparsers.add_parser("harness", help="Harness evidence collection and gate arbitration")
    _set_command_group_help(harness_parser, ("harness",))
    harness_subparsers = harness_parser.add_subparsers(dest="harness_command")

    harness_validate = harness_subparsers.add_parser("validate", help="Validate harness.yaml configuration")
    harness_validate.add_argument("config", nargs="?", default="harness.yaml", help="Path to harness.yaml (default: harness.yaml)")
    harness_validate.set_defaults(func=cmd_harness_validate)

    harness_run = harness_subparsers.add_parser("run", help="Execute harness collection and arbitration")
    harness_run.add_argument("--config", default="harness.yaml", help="Path to harness.yaml (default: harness.yaml)")
    harness_run.add_argument("--json", action="store_true", help="Emit JSON output")
    harness_run.add_argument(
        "--parallel",
        action="store_true",
        help="Run evidence producers in parallel within the harness.yaml limit",
    )
    harness_run.add_argument(
        "--max-workers",
        type=_positive_int,
        default=None,
        help="Requested producer workers when --parallel is set",
    )
    harness_run.set_defaults(func=cmd_harness_run)

    hook_parser = subparsers.add_parser("hook", help="Reusable local hook helpers")
    _set_command_group_help(hook_parser, ("hook",))
    hook_subparsers = hook_parser.add_subparsers(dest="hook_command")

    hook_file_length = hook_subparsers.add_parser(
        "file-length",
        help="Fail when staged or explicit source files exceed the configured line budget",
    )
    hook_file_length.add_argument(
        "--config",
        required=True,
        help="Path to a JSON file with file size budget configuration.",
    )
    hook_file_length.add_argument(
        "--staged-only",
        action="store_true",
        help="Evaluate only staged files from the git index.",
    )
    hook_file_length.add_argument(
        "--strict-limit",
        action="store_true",
        help="Ignore HEAD ratcheting and enforce configured limits directly.",
    )
    hook_file_length.add_argument(
        "--base",
        default="HEAD",
        help="Compatibility flag for changed-only style integrations.",
    )
    hook_file_length.add_argument("files", nargs="*", help="Optional explicit relative paths to evaluate")
    hook_file_length.set_defaults(func=cmd_hook_file_length)

    analyze_parser = subparsers.add_parser("analyze", help="Structured source analysis helpers")
    _set_command_group_help(analyze_parser, ("analyze",))
    analyze_subparsers = analyze_parser.add_subparsers(dest="analyze_command")

    analyze_long_file = analyze_subparsers.add_parser(
        "long-file",
        help="Return ClassMap/FunctionMap payloads for oversized or explicit files",
    )
    analyze_long_file.add_argument(
        "paths",
        nargs="*",
        help="Explicit files to analyze",
    )
    analyze_long_file.add_argument("--files", nargs="*", default=[], help="Explicit files to analyze")
    analyze_long_file.add_argument("--base", default="HEAD", help="Git base reference for implicit oversized-file discovery")
    analyze_long_file.add_argument(
        "--config",
        help="Path to a JSON file with file size budget configuration.",
    )
    analyze_long_file.add_argument(
        "--strict-limit",
        action="store_true",
        help="Ignore HEAD ratcheting and enforce configured limits directly.",
    )
    analyze_long_file.add_argument(
        "--min-lines",
        type=int,
        default=60,
        help="Hide text-report items smaller than this many lines (JSON output is unaffected).",
    )
    analyze_long_file.add_argument(
        "--comment-review-commit-threshold",
        type=int,
        default=5,
        help="Warn when a class/function has comments and changed in at least this many commits.",
    )
    analyze_long_file.add_argument("--json", action="store_true", help="Emit JSON output")
    analyze_long_file.set_defaults(func=cmd_analyze_long_file)

    graph_parser = subparsers.add_parser("graph", help="Graph-backed impact and test-radius analysis")
    _set_command_group_help(graph_parser, ("graph",))
    graph_subparsers = graph_parser.add_subparsers(dest="graph_command")

    graph_build = graph_subparsers.add_parser("build", help="Build or update the code graph")
    graph_build.add_argument("--base", default="HEAD", help="Git diff base for incremental update")
    graph_build.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_build.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_build.set_defaults(func=cmd_graph_build)

    graph_stats = graph_subparsers.add_parser("stats", help="Show graph statistics")
    graph_stats.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_stats.set_defaults(func=cmd_graph_stats)

    graph_impact = graph_subparsers.add_parser("impact", help="Analyze blast radius")
    graph_impact.add_argument("files", nargs="*", help="Optional explicit changed files")
    graph_impact.add_argument("--base", default="HEAD", help="Git diff base")
    graph_impact.add_argument("--depth", type=int, default=2, help="Traversal depth")
    graph_impact.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_impact.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_impact.set_defaults(func=cmd_graph_impact)

    graph_test_radius = graph_subparsers.add_parser(
        "test-radius",
        help="Estimate tests affected by changed files or commits",
    )
    graph_test_radius.add_argument("files", nargs="*", help="Optional explicit changed files")
    graph_test_radius.add_argument("--base", default="HEAD", help="Git diff base")
    graph_test_radius.add_argument("--depth", type=int, default=2, help="Traversal depth")
    graph_test_radius.add_argument("--max-targets", type=int, default=25, help="Max nodes to query")
    graph_test_radius.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_test_radius.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_test_radius.set_defaults(func=cmd_graph_test_radius)

    graph_test_mapping = graph_subparsers.add_parser(
        "test-mapping",
        help="Map changed source files to related tests with heuristic and graph evidence",
    )
    graph_test_mapping.add_argument("files", nargs="*", help="Optional explicit changed files")
    graph_test_mapping.add_argument("--base", default="HEAD", help="Git diff base")
    graph_test_mapping.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode for optional semantic enrichment",
    )
    graph_test_mapping.add_argument(
        "--no-graph",
        action="store_true",
        help="Disable graph enrichment and use heuristic mapping only",
    )
    graph_test_mapping.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Return non-zero when at least one source file has no asserted test mapping",
    )
    graph_test_mapping.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_test_mapping.set_defaults(func=cmd_graph_test_mapping)

    graph_query = graph_subparsers.add_parser("query", help="Run a graph query")
    graph_query.add_argument(
        "pattern",
        choices=[
            "callers_of",
            "callees_of",
            "imports_of",
            "importers_of",
            "children_of",
            "tests_for",
            "inheritors_of",
            "file_summary",
        ],
        help="Query pattern",
    )
    graph_query.add_argument("target", help="Qualified name or file path")
    graph_query.add_argument("--base", default="HEAD", help="Git diff base")
    graph_query.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_query.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_query.set_defaults(func=cmd_graph_query)

    graph_history = graph_subparsers.add_parser(
        "history",
        help="Estimate test radius for recent commits using the current graph",
    )
    graph_history.add_argument("--count", type=int, default=10, help="Number of commits to inspect")
    graph_history.add_argument("--ref", default="HEAD", help="Revision to walk from")
    graph_history.add_argument("--depth", type=int, default=2, help="Traversal depth")
    graph_history.add_argument("--max-targets", type=int, default=25, help="Max nodes to query")
    graph_history.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_history.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_history.set_defaults(func=cmd_graph_history)

    graph_review_context = graph_subparsers.add_parser(
        "review-context",
        help="Build an AI-friendly review context from the current graph",
    )
    graph_review_context.add_argument("files_positional", nargs="*", help="Optional explicit changed files")
    graph_review_context.add_argument("--files", nargs="*", default=[], help="Explicit changed files")
    graph_review_context.add_argument("--base", default="HEAD", help="Git diff base")
    graph_review_context.add_argument("--head", default="HEAD", help="Compatibility flag; currently unused")
    graph_review_context.add_argument("--depth", type=int, default=2, help="Traversal depth")
    graph_review_context.add_argument("--max-targets", type=int, default=25, help="Max nodes to query")
    graph_review_context.add_argument("--max-files", type=int, default=12, help="Max source files to include")
    graph_review_context.add_argument(
        "--max-lines-per-file",
        type=int,
        default=120,
        help="Max source lines to include per file",
    )
    graph_review_context.add_argument(
        "--no-source",
        action="store_true",
        help="Do not include source snippets in the output",
    )
    graph_review_context.add_argument(
        "--build-mode",
        choices=["auto", "full", "skip"],
        default="auto",
        help="Graph build mode",
    )
    graph_review_context.add_argument("--json", action="store_true", help="Emit JSON output")
    graph_review_context.add_argument("--output", help="Write JSON output to a file path or '-' for stdout")
    graph_review_context.set_defaults(func=cmd_graph_review_context)

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """Run Entrix CLI with consistent help and post-success guidance."""
    _configure_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        # 检查是否是子命令组，如果是则显示该组的子命令帮助
        if argv and len(argv) == 1 and argv[0] in ["harness", "graph", "hook", "analyze"]:
            show_subgroup_help(argv[0])
        else:
            print_command_overview()
        return 0

    args.command_path = _command_path(args)
    exit_code = args.func(args)
    if should_show_next_steps(args, exit_code):
        print_next_steps(args.command_path, sys.stderr)
    return exit_code


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
