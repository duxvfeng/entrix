"""Shell runner —— 通过 subprocess 执行 metric 命令。"""

from __future__ import annotations

import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from os import environ
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Callable

from entrix.model import Gate, Metric, MetricResult, ResultState
from entrix.runners.process import process_group_kwargs, terminate_process_tree

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")

# 保留前 4KB 和后 4KB，这样启动上下文和最终的
# 摘要（通过/失败行）在截断后仍然可见。
_OUTPUT_HEAD = 4000
_OUTPUT_TAIL = 4000
_OUTPUT_MAX = _OUTPUT_HEAD + _OUTPUT_TAIL + 200  # a bit of slack


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """Compatibility wrapper for the process-tree terminator."""
    terminate_process_tree(process)


def _smart_truncate(text: str) -> str:
    """保留输出的头部和尾部，使上下文和判定结果都可见。"""
    if len(text) <= _OUTPUT_MAX:
        return text
    head = text[:_OUTPUT_HEAD]
    tail = text[-_OUTPUT_TAIL:]
    omitted = len(text) - _OUTPUT_HEAD - _OUTPUT_TAIL
    return f"{head}\n\n... [{omitted} characters omitted] ...\n\n{tail}"

ProgressCallback = Callable[[str, Metric, MetricResult | None], None]
OutputCallback = Callable[[Metric, str, str], None]


class ShellRunner:
    """以 shell subprocess 方式执行 Metric 命令。"""

    def __init__(
        self,
        project_root: Path,
        timeout: int = 300,
        deadline: float | None = None,
        env_overrides: dict[str, str] | None = None,
        stream_output: bool = False,
        output_callback: OutputCallback | None = None,
    ):
        self.project_root = project_root
        self.timeout = timeout
        self.deadline = deadline
        self.env_overrides = env_overrides or {}
        self.stream_output = stream_output
        self.output_callback = output_callback

    def run(self, metric: Metric, *, dry_run: bool = False) -> MetricResult:
        """执行单个 metric 的 shell 命令。

        返回 MetricResult，根据 regex pattern 匹配或进程 exit code 判定通过/失败。
        """
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
                output=f"[DRY-RUN] Would run: {metric.command}",
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
            if self.stream_output and self.output_callback is not None:
                output, returncode = self._run_streaming(metric, timeout=timeout)
            else:
                output, returncode = self._run_captured(metric, timeout=timeout)

            clean_output = _ANSI_ESCAPE.sub("", output)

            if metric.pattern:
                pattern_matched = bool(re.search(metric.pattern, clean_output, re.IGNORECASE))
                # 以 exit code 优先的混合策略：非零退出码一定判定为失败。
                # 当 exit code 为 0 时，pattern 匹配结果作为补充依据。
                passed = (returncode == 0) and pattern_matched
            else:
                passed = returncode == 0

            elapsed = (time.monotonic() - start) * 1000

            # 判定结果状态：区分检查器基础设施错误
            # 与真实的产品失败。
            state: ResultState | None = None
            if passed:
                state = ResultState.PASS
            elif returncode != 0 and metric.pattern and not pattern_matched:
                # exit code 和 pattern 同时失败——很可能是基础设施
                # 错误（文件缺失、崩溃、栈溢出等）
                state = ResultState.UNKNOWN
            else:
                state = ResultState.FAIL

            return MetricResult(
                metric_name=metric.name,
                passed=passed,
                output=_smart_truncate(clean_output),
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
                duration_ms=elapsed,
                state=state,
                returncode=returncode,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - start) * 1000
            return MetricResult(
                metric_name=metric.name,
                passed=False,
                output=f"TIMEOUT ({timeout}s)",
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
                duration_ms=elapsed,
                state=ResultState.UNKNOWN,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return MetricResult(
                metric_name=metric.name,
                passed=False,
                output=str(e),
                tier=metric.tier,
                hard_gate=metric.gate == Gate.HARD,
                duration_ms=elapsed,
                state=ResultState.UNKNOWN,
            )

    def _run_captured(self, metric: Metric, *, timeout: int) -> tuple[str, int]:
        command, use_shell = self._shell_command(metric.command)
        process = subprocess.Popen(
            command,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=self.project_root,
            env={**environ, **self.env_overrides},
            **process_group_kwargs(),
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise
        return stdout + stderr, process.returncode

    def _run_streaming(self, metric: Metric, *, timeout: int) -> tuple[str, int]:
        command, use_shell = self._shell_command(metric.command)
        process = subprocess.Popen(
            command,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=self.project_root,
            env={**environ, **self.env_overrides},
            **process_group_kwargs(),
        )
        queue: Queue[tuple[str, str | None]] = Queue()
        chunks: list[str] = []

        def pump(stream, source: str) -> None:
            if stream is None:
                queue.put((source, None))
                return
            try:
                for line in iter(stream.readline, ""):
                    queue.put((source, line))
            finally:
                stream.close()
                queue.put((source, None))

        streams = {
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        threads = [
            Thread(target=pump, args=(stream, source), daemon=True)
            for source, stream in streams.items()
        ]
        for thread in threads:
            thread.start()

        closed_streams = 0
        deadline = time.monotonic() + timeout
        while closed_streams < len(threads):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process_tree(process)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass
                raise subprocess.TimeoutExpired(metric.command, timeout)
            try:
                source, chunk = queue.get(timeout=min(0.1, remaining))
            except Empty:
                continue
            if chunk is None:
                closed_streams += 1
                continue
            chunks.append(chunk)
            self._emit_output(metric, source, chunk)

        try:
            returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
            raise subprocess.TimeoutExpired(metric.command, timeout)
        for thread in threads:
            thread.join(timeout=0.1)
        return "".join(chunks), returncode

    @staticmethod
    def _shell_command(command: str) -> tuple[str | list[str], bool]:
        if os.name == "nt":
            return command, True
        return ["/bin/bash", "-lc", command], False

    def _emit_output(self, metric: Metric, source: str, line: str) -> None:
        if self.output_callback is not None:
            self.output_callback(metric, source, line)

    def run_batch(
        self,
        metrics: list[Metric],
        *,
        parallel: bool = False,
        dry_run: bool = False,
        max_workers: int = 4,
        progress_callback: ProgressCallback | None = None,
    ) -> list[MetricResult]:
        """执行多个 metric，可选择并行执行。

        返回结果与输入 metric 的顺序一致。
        """
        if not parallel or dry_run:
            sequential_results: list[MetricResult] = []
            for metric in metrics:
                self._emit_progress(progress_callback, "start", metric)
                result = self.run(metric, dry_run=dry_run)
                self._emit_progress(progress_callback, "end", metric, result)
                sequential_results.append(result)
            return sequential_results

        results: dict[int, MetricResult] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for i, metric in enumerate(metrics):
                self._emit_progress(progress_callback, "start", metric)
                futures[executor.submit(self.run, metric)] = (i, metric)
            for future in as_completed(futures):
                idx, metric = futures[future]
                result = future.result()
                self._emit_progress(progress_callback, "end", metric, result)
                results[idx] = result

        return [results[i] for i in range(len(metrics))]

    def _emit_progress(
        self,
        callback: ProgressCallback | None,
        event: str,
        metric: Metric,
        result: MetricResult | None = None,
    ) -> None:
        if callback is not None:
            callback(event, metric, result)
