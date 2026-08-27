"""Release 域 CLI 命令 —— release-trigger 评估。

从 ``entrix.cli`` 拆出的增量模块：仅含 release-trigger 命令实现与
专用输出函数，argparse 接线仍由 ``build_parser()`` 负责。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from entrix.presets import get_project_preset
from entrix.release_trigger import (
    evaluate_release_triggers,
    load_release_manifest,
    load_release_triggers,
)
from entrix.review_trigger import collect_changed_files as collect_review_changed_files


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


def _find_release_trigger_config(project_root: Path) -> Path:
    """定位默认的 release-trigger config。"""
    config_path = get_project_preset().release_trigger_config(project_root)
    if not config_path.is_file():
        print(f"错误: 在 {config_path} 未找到 release-trigger 配置")
        sys.exit(1)
    return config_path


def _print_release_trigger_report(report: dict) -> None:
    print("Release trigger report")
    print(f"- blocked: {'yes' if report.get('blocked') else 'no'}")
    print(
        "- human review required: "
        f"{'yes' if report.get('human_review_required') else 'no'}"
    )
    print(f"- manifest: {report.get('manifest_path')}")
    if report.get("baseline_manifest_path"):
        print(f"- baseline manifest: {report['baseline_manifest_path']}")
    print(f"- artifacts: {len(report.get('artifacts', []))}")
    print(f"- changed files: {len(report.get('changed_files', []))}")
    triggers = report.get("triggers", [])
    if not triggers:
        print("- triggers: none")
        return
    print("- triggers:")
    for trigger in triggers:
        print(
            f"  - {trigger['name']} [{trigger['severity']}] "
            f"-> {trigger['action']}"
        )
        for reason in trigger.get("reasons", []):
            print(f"    - {reason}")


def cmd_release_trigger(args: argparse.Namespace) -> int:
    """针对 release manifest 评估 release-trigger 规则。"""
    project_root = _find_project_root()
    config_path = Path(args.config).resolve() if args.config else _find_release_trigger_config(project_root)

    rules = load_release_triggers(config_path)
    manifest_path = Path(args.manifest).resolve()
    manifest_label, artifacts = load_release_manifest(manifest_path)
    baseline_artifacts = ()
    baseline_manifest_label: str | None = None
    if args.baseline_manifest:
        baseline_manifest_path = Path(args.baseline_manifest).resolve()
        baseline_manifest_label, baseline_artifacts = load_release_manifest(baseline_manifest_path)
    changed_files = args.files or collect_review_changed_files(project_root, args.base)
    report = evaluate_release_triggers(
        rules,
        artifacts,
        manifest_path=manifest_label,
        changed_files=changed_files,
        baseline_artifacts=baseline_artifacts,
        baseline_manifest_path=baseline_manifest_label,
    )

    if args.json:
        _print_json(report.to_dict())
    else:
        _print_release_trigger_report(report.to_dict())

    if args.fail_on_trigger:
        if report.blocked:
            return 4
        if report.human_review_required:
            return 3
    return 0
