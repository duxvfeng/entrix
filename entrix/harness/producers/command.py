"""Command-based evidence producers."""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone

from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.evidence import Evidence
from entrix.harness.parsers import get_parser
from entrix.harness.parsers.base import ParserContext, collect_artifacts
from entrix.harness.producers.base import Producer, ProducerContext
from entrix.runners.process import process_group_kwargs, terminate_process_tree


class CommandProducer(Producer):
    """Producer that runs shell commands and parses output."""

    def __init__(self, config: EvidenceProducerConfig) -> None:
        """Initialize the command producer.

        Args:
            config: Producer configuration
        """
        self.config = config
        self.parser_type = config.parser.get("type", "exit_code")

    def run(self, context: ProducerContext) -> Evidence:
        """Execute command and parse result.

        Args:
            context: Execution context

        Returns:
            Evidence object containing parsed results
        """
        evidence = Evidence(
            id=self.config.id,
            type=self.config.type,
            name=self.config.name,
            producer=self.config.producer,
            task_id=context.task_id,
            started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        try:
            # Execute command
            assert self.config.command is not None
            start_time = time.time()
            process = subprocess.Popen(
                self.config.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=context.repo_root,
                **process_group_kwargs(),
            )
            timeout = float(self.config.timeout_seconds)
            if context.deadline is not None:
                timeout = min(timeout, context.deadline - time.monotonic())
                if timeout <= 0:
                    raise subprocess.TimeoutExpired(self.config.command, timeout)
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
            duration_ms = int((time.time() - start_time) * 1000)
            evidence.duration_ms = duration_ms
            result = subprocess.CompletedProcess(
                self.config.command,
                process.returncode,
                stdout,
                stderr,
            )

            parser = get_parser(str(self.parser_type))
            parsed = parser.parse(
                ParserContext(
                    repo_root=context.repo_root,
                    config=self.config.parser,
                    completed_process=result,
                )
            )
            evidence.status = parsed.status
            evidence.summary = parsed.summary
            evidence.raw = parsed.raw
            evidence.artifacts = parsed.artifacts + collect_artifacts(
                context.repo_root, self.config.artifacts
            )

        except subprocess.TimeoutExpired:
            evidence.status = "timeout"
            evidence.raw = {"error": f"Command timed out after {self.config.timeout_seconds}s or the Stop Gate deadline"}
        except Exception as e:
            evidence.status = "error"
            evidence.raw = {"error": str(e)}

        return evidence
