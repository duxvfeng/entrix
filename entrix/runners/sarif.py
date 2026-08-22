"""SARIF runner —— 从 SARIF evidence 评估 metric。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from os import environ
from pathlib import Path
from typing import Any

from entrix.model import Gate, Metric, MetricResult, ResultState
from entrix.runners.process import process_group_kwargs, terminate_process_tree


class SarifRunner:
    """从文件路径或命令 stdout 加载 SARIF evidence，并评估发现。"""

    def __init__(
        self,
        project_root: Path,
        timeout: int = 300,
        deadline: float | None = None,
        env_overrides: dict[str, str] | None = None,
    ):
        self.project_root = project_root
        self.timeout = timeout
        self.deadline = deadline
        self.env_overrides = env_overrides or {}

    def run(self, metric: Metric, *, dry_run: bool = False) -> MetricResult:
        """执行 SARIF metric 并将其评估为 PASS/FAIL/UNKNOWN。"""
        if metric.waiver and metric.waiver.is_active():
            return MetricResult(
                metric_name=metric.name,
                passed=True,
                output=f"[WAIVED] {metric.waiver.reason}",
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
                state=ResultState.WAIVED,
            )

        if dry_run:
            return MetricResult(
                metric_name=metric.name,
                passed=True,
                output=f"[DRY-RUN] Would read SARIF evidence: {metric.command}",
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
            )

        start = time.monotonic()
        timeout = metric.timeout_seconds or self.timeout
        if self.deadline is not None:
            timeout = min(float(timeout), self.deadline - time.monotonic())
            if timeout <= 0:
                return MetricResult(
                    metric_name=metric.name,
                    passed=False,
                    output="STOP GATE DEADLINE EXCEEDED",
                    tier=metric.tier,
                    hard_gate=metric.gate == Gate.HARD,
                    state=ResultState.UNKNOWN,
                )
        try:
            payload = self._load_payload(metric.command, timeout=timeout)
            summary = _summarize_sarif(payload)
            summary_line = (
                f"sarif_runs={summary['runs']} "
                f"sarif_results={summary['results']} "
                f"sarif_errors={summary['errors']} "
                f"sarif_warnings={summary['warnings']} "
                f"sarif_notes={summary['notes']}"
            )
            if metric.pattern:
                passed = bool(re.search(metric.pattern, summary_line, re.IGNORECASE))
            else:
                passed = summary["errors"] == 0
            elapsed = (time.monotonic() - start) * 1000
            return MetricResult(
                metric_name=metric.name,
                passed=passed,
                output=summary_line,
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - start) * 1000
            return MetricResult(
                metric_name=metric.name,
                passed=False,
                output=f"SARIF TIMEOUT ({timeout}s)",
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
                duration_ms=elapsed,
                state=ResultState.UNKNOWN,
            )
        except Exception as error:
            elapsed = (time.monotonic() - start) * 1000
            return MetricResult(
                metric_name=metric.name,
                passed=False,
                output=f"SARIF parse error: {error}",
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
                duration_ms=elapsed,
                state=ResultState.UNKNOWN,
            )

    def run_batch(self, metrics: list[Metric], *, dry_run: bool = False) -> list[MetricResult]:
        """按顺序执行多个 SARIF metric。"""
        return [self.run(metric, dry_run=dry_run) for metric in metrics]

    def _load_payload(self, command: str, *, timeout: float) -> dict[str, Any]:
        # 如果 command 解析为已存在的文件路径，则将其视为 SARIF 文件输入。
        candidate = (self.project_root / command).resolve()
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("SARIF root must be an object")
            return data

        if os.name == "nt":
            process_command: str | list[str] = command
            use_shell = True
        else:
            process_command = ["/bin/bash", "-lc", command]
            use_shell = False
        process = subprocess.Popen(
            process_command,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.project_root,
            env={**environ, **self.env_overrides},
            **process_group_kwargs(),
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_process_tree(process)
            try:
                process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            raise
        if process.returncode != 0:
            detail = stderr.strip() or f"exit code {process.returncode}"
            raise RuntimeError(f"SARIF command failed: {detail}")
        parsed = _parse_json_from_text(stdout)
        if not isinstance(parsed, dict):
            raise ValueError("SARIF stdout did not contain a JSON object")
        return parsed


def _parse_json_from_text(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty stdout")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def _summarize_sarif(payload: dict[str, Any]) -> dict[str, int]:
    runs = payload.get("runs")
    if not isinstance(runs, list):
        raise ValueError("SARIF payload missing runs[]")

    counts = {
        "runs": len(runs),
        "results": 0,
        "errors": 0,
        "warnings": 0,
        "notes": 0,
    }
    for run in runs:
        if not isinstance(run, dict):
            continue
        results = run.get("results") or []
        if not isinstance(results, list):
            continue
        counts["results"] += len(results)
        for result in results:
            level = ""
            if isinstance(result, dict):
                raw_level = result.get("level")
                if isinstance(raw_level, str):
                    level = raw_level.lower()
            if level == "error":
                counts["errors"] += 1
            elif level == "note":
                counts["notes"] += 1
            else:
                counts["warnings"] += 1
    return counts
