"""Regression tests for the repository's VS Code Git tasks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tasks() -> list[dict]:
    payload = json.loads((ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    return payload["tasks"]


def test_tasks_only_define_current_branch_and_tag_pushes() -> None:
    tasks = _tasks()
    labels = {task["label"] for task in tasks}

    assert labels == {
        "Git: 推送 GitHub（不带 tag）",
        "Git: 推送 Gitee（不带 tag）",
        "Git: 一键推送 GitHub + Gitee（不带 tag）",
        "Git: 推送当前 tag 到 GitHub",
        "Git: 推送当前 tag 到 Gitee",
        "Git: 一键推送当前 tag 到 GitHub + Gitee",
        "Git: 一键推送代码 + 当前 tag 到 GitHub + Gitee",
    }
    assert all("dxf" not in json.dumps(task, ensure_ascii=False) for task in tasks)
    assert all("所有分支" not in task["label"] for task in tasks)


def test_single_remote_tasks_use_expected_push_commands() -> None:
    tasks = {task["label"]: task for task in _tasks()}

    assert tasks["Git: 推送 GitHub（不带 tag）"]["args"] == ["push", "github", "HEAD"]
    assert tasks["Git: 推送 Gitee（不带 tag）"]["args"] == ["push", "origin", "HEAD"]
    assert tasks["Git: 推送当前 tag 到 GitHub"]["args"] == [
        "scripts/push_current_tag.py",
        "--remote",
        "github",
    ]
    assert tasks["Git: 推送当前 tag 到 Gitee"]["args"] == [
        "scripts/push_current_tag.py",
        "--remote",
        "origin",
    ]


def test_combined_tasks_run_single_remote_tasks_in_sequence() -> None:
    tasks = {task["label"]: task for task in _tasks()}

    assert tasks["Git: 一键推送 GitHub + Gitee（不带 tag）"]["dependsOrder"] == "sequence"
    assert tasks["Git: 一键推送 GitHub + Gitee（不带 tag）"]["dependsOn"] == [
        "Git: 推送 GitHub（不带 tag）",
        "Git: 推送 Gitee（不带 tag）",
    ]
    assert tasks["Git: 一键推送当前 tag 到 GitHub + Gitee"]["dependsOrder"] == "sequence"
    assert tasks["Git: 一键推送当前 tag 到 GitHub + Gitee"]["dependsOn"] == [
        "Git: 推送当前 tag 到 GitHub",
        "Git: 推送当前 tag 到 Gitee",
    ]
    assert tasks["Git: 一键推送代码 + 当前 tag 到 GitHub + Gitee"]["dependsOrder"] == "sequence"
    assert tasks["Git: 一键推送代码 + 当前 tag 到 GitHub + Gitee"]["dependsOn"] == [
        "Git: 一键推送 GitHub + Gitee（不带 tag）",
        "Git: 一键推送当前 tag 到 GitHub + Gitee",
    ]
