"""Graph 子命令的输出渲染与处理逻辑，从 cli.py 拆出。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from entrix.cli_runtime import print_json
from entrix.gitinfo import find_project_root
from entrix.runners.graph import GraphRunner
from entrix.test_mapping import analyze_test_mappings


def _print_graph_impact(result: dict) -> None:
    print(result.get("summary", "No summary available."))
    print(f"Changed files: {len(result.get('changed_files', []))}")
    print(f"Impacted files: {len(result.get('impacted_files', []))}")
    print(f"Impacted test files: {len(result.get('impacted_test_files', []))}")
    print(f"Wide blast radius: {'yes' if result.get('wide_blast_radius') else 'no'}")
    if result.get("skipped_files"):
        print(f"Skipped files: {', '.join(result['skipped_files'][:10])}")


def _print_graph_test_radius(result: dict) -> None:
    print(result.get("summary", "No summary available."))
    print(f"Changed files: {len(result.get('changed_files', []))}")
    print(f"Queryable targets: {len(result.get('target_nodes', []))}")
    print(f"Unique test files: {len(result.get('test_files', []))}")
    print(f"Untested targets: {len(result.get('untested_targets', []))}")
    if result.get("test_files"):
        print("Test files:")
        for file_path in result["test_files"][:20]:
            print(f"  - {file_path}")
    if result.get("untested_targets"):
        print("Untested targets:")
        for target in result["untested_targets"][:20]:
            print(f"  - {target['qualified_name']}")


def _print_graph_test_mapping(result: dict) -> None:
    print(result.get("summary", "No summary available."))
    print(f"Changed files: {len(result.get('changed_files', []))}")
    print(f"Skipped changed test files: {len(result.get('skipped_test_files', []))}")
    counts = result.get("status_counts", {})
    if counts:
        ordered = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
        print(f"Statuses: {ordered}")
    resolver_counts = result.get("resolver_counts", {})
    if resolver_counts:
        ordered = ", ".join(f"{key}={resolver_counts[key]}" for key in sorted(resolver_counts))
        print(f"Resolvers: {ordered}")
    graph = result.get("graph", {})
    print(
        "Graph enrichment: "
        f"{'on' if graph.get('available') else 'off'} "
        f"({graph.get('status', 'unknown')})"
    )
    for item in result.get("mappings", [])[:20]:
        related = item.get("related_test_files", [])
        related_preview = ", ".join(related[:3]) if related else "-"
        print(
            f"- {item['source_file']} [{item['language']}] "
            f"status={item['status']} resolver={item['resolver_kind']} "
            f"tests={related_preview}"
        )


def _print_graph_query(result: dict) -> None:
    print(result.get("summary", "No summary available."))
    for item in result.get("results", [])[:20]:
        label = item.get("qualified_name") or item.get("name") or item.get("file_path") or str(item)
        print(f"  - {label}")


def _print_graph_history(result: dict) -> None:
    print(result.get("summary", "No summary available."))
    for commit in result.get("commits", []):
        print(
            f"{commit['short_commit']} {commit['subject']} | "
            f"files={commit['changed_file_count']} "
            f"targets={commit['target_count']} "
            f"tests={commit['test_file_count']} "
            f"untested={commit['untested_target_count']}"
        )


def _print_graph_review_context(result: dict) -> None:
    print(result.get("summary", "No summary available."))
    context = result.get("context", {})
    tests = context.get("tests", {})
    print(f"Changed files: {len(context.get('changed_files', []))}")
    print(f"Impacted files: {len(context.get('impacted_files', []))}")
    print(f"Queryable targets: {len(context.get('targets', []))}")
    print(f"Test files: {len(tests.get('test_files', []))}")
    print("Review guidance:")
    for line in str(context.get("review_guidance", "")).splitlines():
        print(f"  {line}")
    snippets = context.get("source_snippets", [])
    if snippets:
        print("Source snippets:")
        for snippet in snippets[:10]:
            suffix = " (truncated)" if snippet.get("truncated") else ""
            print(f"  - {snippet['file_path']}{suffix}")


def cmd_graph_build(args: argparse.Namespace) -> int:
    """构建或更新底层 code graph。"""
    runner = GraphRunner(find_project_root())
    result = runner.build_graph(base=args.base, build_mode=args.build_mode)
    if args.json:
        print_json(result)
    else:
        print(result.get("summary", result.get("reason", "No summary available.")))
    return 0 if result.get("status") not in {"unavailable"} else 1


def cmd_graph_stats(args: argparse.Namespace) -> int:
    """显示 graph 统计信息。"""
    runner = GraphRunner(find_project_root())
    result = runner.stats()
    if args.json:
        print_json(result)
    else:
        if result.get("status") == "unavailable":
            print(result.get("reason", "Graph unavailable"))
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") != "unavailable" else 1


def cmd_graph_impact(args: argparse.Namespace) -> int:
    """显示变更文件或显式文件列表的 blast radius。"""
    runner = GraphRunner(find_project_root())
    result = runner.analyze_impact(
        args.files or None,
        base=args.base,
        max_depth=args.depth,
        build_mode=args.build_mode,
    )
    if args.json:
        print_json(result)
    else:
        if result.get("status") == "unavailable":
            print(result.get("reason", "Graph unavailable"))
            return 1
        _print_graph_impact(result)
    return 0 if result.get("status") != "unavailable" else 1


def cmd_graph_test_radius(args: argparse.Namespace) -> int:
    """显示当前 diff 或显式文件的 test radius 内的 tests。"""
    runner = GraphRunner(find_project_root())
    result = runner.analyze_test_radius(
        args.files or None,
        base=args.base,
        max_depth=args.depth,
        build_mode=args.build_mode,
        max_targets=args.max_targets,
    )
    if args.json:
        print_json(result)
    else:
        if result.get("status") == "unavailable":
            print(result.get("reason", "Graph unavailable"))
            return 1
        _print_graph_test_radius(result)
    return 0 if result.get("status") != "unavailable" else 1


def cmd_graph_test_mapping(args: argparse.Namespace) -> int:
    """显示变更文件的跨语言 source-to-test mappings。"""
    result = analyze_test_mappings(
        find_project_root(),
        args.files or None,
        base=args.base,
        use_graph=not args.no_graph,
        build_mode=args.build_mode,
    )
    if args.json:
        print_json(result)
    else:
        _print_graph_test_mapping(result)
    missing_mappings = int((result.get("status_counts") or {}).get("missing", 0))
    if args.fail_on_missing and missing_mappings > 0:
        return 2
    return 0


def cmd_graph_query(args: argparse.Namespace) -> int:
    """运行 graph query，例如 callers_of 或 tests_for。"""
    runner = GraphRunner(find_project_root())
    result = runner.query(
        args.pattern,
        args.target,
        base=args.base,
        build_mode=args.build_mode,
    )
    if args.json:
        print_json(result)
    else:
        if result.get("status") == "unavailable":
            print(result.get("reason", "Graph unavailable"))
            return 1
        _print_graph_query(result)
    return 0 if result.get("status") != "unavailable" else 1


def cmd_graph_history(args: argparse.Namespace) -> int:
    """使用当前 graph 估算最近 commits 的 test radius。"""
    runner = GraphRunner(find_project_root())
    result = runner.analyze_history(
        count=args.count,
        ref=args.ref,
        max_depth=args.depth,
        build_mode=args.build_mode,
        max_targets=args.max_targets,
    )
    if args.json:
        print_json(result)
    else:
        if result.get("status") == "unavailable":
            print(result.get("reason", "Graph unavailable"))
            return 1
        _print_graph_history(result)
    return 0 if result.get("status") != "unavailable" else 1


def cmd_graph_review_context(args: argparse.Namespace) -> int:
    """为当前 diff 或文件构建 AI-friendly 的 review context。"""
    runner = GraphRunner(find_project_root())
    file_args = (args.files_positional or []) + (args.files or [])
    result = runner.review_context(
        file_args or None,
        base=args.base,
        max_depth=args.depth,
        build_mode=args.build_mode,
        max_targets=args.max_targets,
        include_source=not args.no_source,
        max_files=args.max_files,
        max_lines_per_file=args.max_lines_per_file,
    )
    if args.json:
        if args.output and args.output != "-":
            Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            print_json(result)
    else:
        if result.get("status") == "unavailable":
            print(result.get("reason", "Graph unavailable"))
            return 1
        _print_graph_review_context(result)
    return 0 if result.get("status") != "unavailable" else 1
