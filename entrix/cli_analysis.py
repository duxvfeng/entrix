"""分析类 CLI 命令 —— 长文件结构与 file-length guard。

从 ``entrix.cli`` 拆出的增量模块：仅含 analyze/hook 域的命令实现与
专用输出函数，argparse 接线仍由 ``build_parser()`` 负责。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from entrix.analysis.long_file import analyze_long_files
from entrix.file_budgets import evaluate_paths, is_tracked_source_file, load_config


def _find_project_root() -> Path:
    """从 CWD 向上遍历，查找常见项目或 Harness 根目录。"""
    cwd = Path.cwd().resolve()
    markers = (
        "harness.yaml",
        ".harness/harness.yaml",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    )
    for parent in [cwd, *cwd.parents]:
        if any((parent / marker).exists() for marker in markers):
            return parent
    return cwd


def _print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _format_line_span(item: dict) -> str:
    return f"L{item['startLine']}-{item['endLine']}, {item['lineCount']}"


def _format_compact_items(items: list[dict]) -> str:
    return ", ".join(f"{item['name']} ({_format_line_span(item)})" for item in items)


def _sort_structure_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda item: (-item["lineCount"], item["startLine"], item["name"]))


def _print_hook_long_file_summary(
    result: dict,
    *,
    max_classes: int = 3,
    max_methods_per_class: int = 4,
    max_functions: int = 5,
) -> None:
    files = result.get("files", [])
    if not files:
        print("Structure summary unavailable: no supported files for structural analysis.")
        return

    print("Structure summary (tree-sitter symbols):")
    for item in files:
        file_path = item.get("filePath", "<unknown>")
        if item.get("status") not in {None, "ok"}:
            print(f"- {file_path}: {item.get('summary', 'analysis failed')}")
            continue

        print(f"- {file_path}")
        classes = _sort_structure_items(item.get("classes", []))
        functions = _sort_structure_items(item.get("functions", []))

        if not classes and not functions:
            print("  no class/function symbols found")
            continue

        for cls in classes[:max_classes]:
            print(
                f"  class {cls['name']} "
                f"({_format_line_span(cls)}, methods={cls.get('methodCount', 0)})"
            )
            methods = _sort_structure_items(cls.get("methods", []))
            for method in methods[:max_methods_per_class]:
                print(f"    method {method['name']} ({_format_line_span(method)})")
            remaining_methods = len(methods) - max_methods_per_class
            if remaining_methods > 0:
                print(f"    ... {remaining_methods} more method(s)")

        remaining_classes = len(classes) - max_classes
        if remaining_classes > 0:
            print(f"  ... {remaining_classes} more class(es)")

        if functions:
            print(f"  functions: {_format_compact_items(functions[:max_functions])}")
            remaining_functions = len(functions) - max_functions
            if remaining_functions > 0:
                print(f"  ... {remaining_functions} more function(s)")

        warnings = item.get("warnings", [])
        if warnings:
            print(f"  review-warnings: {len(warnings)}")


def _print_long_file_analysis(result: dict, *, min_lines: int = 60) -> None:
    files = result.get("files", [])
    if not files:
        print("No oversized files detected.")
        return
    for item in files:
        if item.get("status") not in {None, "ok"}:
            print(f"{item['filePath']}: {item.get('summary', 'analysis failed')}")
            continue
        status_line = (
            f"{item['filePath']} exceeds budget {item['budgetLimit']} with {item['lineCount']} lines"
            if item.get("overBudget")
            else f"{item['filePath']} has {item['lineCount']} lines (budget {item['budgetLimit']})"
        )
        print(status_line)
        print(f"History: commits={item.get('commitCount', 0)}")
        warnings = item.get("warnings", [])
        if warnings:
            print(f"Warnings: {len(warnings)}")
            for warning in warnings:
                print(
                    "- review comments in "
                    f"{warning['symbolKind']} {warning['name']} "
                    f"({_format_line_span(warning)}) commits={warning['commitCount']} "
                    f"comments={warning['commentCount']}"
                )

        classes = sorted(
            item.get("classes", []),
            key=lambda cls: (cls["startLine"], cls["name"]),
        )
        functions = sorted(
            item.get("functions", []),
            key=lambda fn: (fn["startLine"], fn["name"]),
        )
        print(f"Classes: {len(classes)}")
        if classes:
            for cls in classes:
                print(f"- {cls['name']} ({_format_line_span(cls)})")
        else:
            print("- none")

        print("")
        print(f"Functions: {len(functions)}")
        if not functions:
            print("- none")
            continue

        large = [fn for fn in functions if fn["lineCount"] >= min_lines]
        small = [fn for fn in functions if fn["lineCount"] <= 10]
        medium = [fn for fn in functions if 10 < fn["lineCount"] < min_lines]

        if small:
            print(f"- Small helpers: {_format_compact_items(small)}")
        if medium:
            print(f"- Medium: {_format_compact_items(medium)}")
        if large:
            print(f"- Large: {_format_compact_items(large)}")


def cmd_hook_file_length(args: argparse.Namespace) -> int:
    """运行一个可复用的 file-length guard，适用于 pre-commit hooks。"""
    project_root = _find_project_root()
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    relative_paths = args.files or []
    if not relative_paths:
        file_budget_args = argparse.Namespace(
            changed_only=False,
            staged_only=args.staged_only,
            base=args.base,
            overrides_only=False,
            paths=[],
        )
        from entrix.file_budgets import _resolve_paths

        relative_paths = _resolve_paths(file_budget_args, project_root, config)

    violations = evaluate_paths(
        project_root,
        relative_paths,
        config,
        use_head_ratchet=not args.strict_limit,
    )

    checked_count = sum(
        1 for path in set(relative_paths) if is_tracked_source_file(path, config)
    )
    print(f"file_budget_checked: {checked_count}")
    print(f"file_budget_violations: {len(violations)}")
    for violation in violations:
        reason = f" | {violation.reason}" if violation.reason else ""
        print(
            f"current file length {violation.line_count} exceeds limit "
            f"{violation.max_lines}: {violation.path}{reason}"
        )
    if violations:
        print("Refactor the oversized file before commit.")
        structure_result = analyze_long_files(
            project_root,
            files=list(dict.fromkeys(violation.path for violation in violations)),
            config_path=config_path,
            base=args.base,
            use_head_ratchet=not args.strict_limit,
        )
        if structure_result.get("status") == "unavailable":
            print(
                "Structure summary unavailable: "
                f"{structure_result.get('summary', 'long-file analysis unavailable')}"
            )
        else:
            _print_hook_long_file_summary(structure_result)
        return 1
    return 0


def cmd_analyze_long_file(args: argparse.Namespace) -> int:
    """将超大或显式文件分析为 ClassMap/FunctionMap payload。"""
    project_root = _find_project_root()
    explicit_files = list(dict.fromkeys((args.files or []) + (args.paths or [])))
    result = analyze_long_files(
        project_root,
        files=explicit_files or None,
        config_path=Path(args.config).resolve() if args.config else None,
        base=args.base,
        use_head_ratchet=not args.strict_limit,
        comment_review_commit_threshold=args.comment_review_commit_threshold,
    )
    if result.get("status") == "unavailable":
        print(result.get("summary", "Long-file analysis unavailable"))
        return 1
    if args.json:
        _print_json(result)
    else:
        _print_long_file_analysis(result, min_lines=args.min_lines)
    return 0
