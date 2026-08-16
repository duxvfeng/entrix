"""Command-based evidence producers."""
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from entrix.harness.producers.base import Producer, ProducerContext
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.evidence import Evidence


class CommandProducer(Producer):
    """Producer that runs shell commands and parses output."""

    def __init__(self, config: EvidenceProducerConfig) -> None:
        """Initialize the command producer.

        Args:
            config: Producer configuration
        """
        self.config = config
        self.parser_type = config.parser.get("type", "exit_code")
        self.regex_pattern = config.parser.get("pattern")

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
            start_time = time.time()
            result = subprocess.run(
                self.config.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=context.repo_root,
            )
            duration_ms = int((time.time() - start_time) * 1000)
            evidence.duration_ms = duration_ms

            # Parse based on parser type
            if self.parser_type == "exit_code":
                self._parse_exit_code(result, evidence)
            elif self.parser_type == "regex":
                self._parse_regex(result, evidence)
            else:
                evidence.status = "error"
                evidence.raw = {"error": f"Unknown parser type: {self.parser_type}"}

        except subprocess.TimeoutExpired:
            evidence.status = "timeout"
            evidence.raw = {"error": f"Command timed out after {self.config.timeout_seconds}s"}
        except Exception as e:
            evidence.status = "error"
            evidence.raw = {"error": str(e)}

        return evidence

    def _parse_exit_code(self, result: subprocess.CompletedProcess, evidence: Evidence) -> None:
        """Parse command result using exit code."""
        evidence.raw = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

        if result.returncode == 0:
            evidence.status = "pass"
        else:
            evidence.status = "fail"

    def _parse_regex(self, result: subprocess.CompletedProcess, evidence: Evidence) -> None:
        """Parse command result using regex pattern."""
        evidence.raw = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

        if not self.regex_pattern:
            evidence.status = "error"
            evidence.raw = {"error": "Regex parser requires pattern"}
            return

        try:
            match = re.search(self.regex_pattern, result.stdout)
            if match:
                evidence.status = "pass"
                evidence.summary = match.groupdict()
            else:
                evidence.status = "error"
                evidence.raw = {"error": "Regex pattern did not match output"}
        except re.error as e:
            evidence.status = "error"
            evidence.raw = {"error": f"Regex error: {e}"}