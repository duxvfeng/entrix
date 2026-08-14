"""证据收集器 - 独立收集质量检查证据"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone

from entrix.engine import run_fitness_report
from entrix.governance import GovernancePolicy
from entrix.presets import get_project_preset
from entrix.review_trigger import (
    collect_changed_files,
    collect_diff_stats,
    evaluate_review_triggers,
    load_review_triggers,
)
from entrix.stop_gate.errors import EvidenceCollectionError, TimeoutError
from entrix.stop_gate.model import EvidencePack, GateAttempt


class EvidenceCollector:
    """收集质量检查证据，独立于 Claude 进程执行"""

    def __init__(self, timeout_seconds: int = 300):
        self.timeout_seconds = timeout_seconds

    def collect_evidence(self, attempt: GateAttempt) -> EvidencePack:
        """收集完整的证据包"""
        start_time = time.time()
        evidence_pack = EvidencePack(attempt_id=attempt.attempt_id)

        # 1. 收集环境证据（失败不应阻止后续检查）
        try:
            self._collect_environment_evidence(attempt, evidence_pack)
        except TimeoutError:
            evidence_pack.collection_errors.append({
                "component": "environment",
                "error": "环境证据收集超时",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:  # noqa: BLE001
            evidence_pack.collection_errors.append({
                "component": "environment",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # 2. 运行 Entrix fitness 检查
        try:
            self._collect_fitness_evidence(attempt, evidence_pack)
        except TimeoutError:
            evidence_pack.fitness = {"status": "timeout", "error": "检查超时"}
            evidence_pack.collection_errors.append({
                "component": "fitness",
                "error": "fitness 检查超时",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:  # noqa: BLE001
            evidence_pack.fitness = {"status": "error", "error": str(e)}

        # 3. 运行 review trigger
        try:
            self._collect_review_trigger_evidence(attempt, evidence_pack)
        except Exception as e:  # noqa: BLE001
            evidence_pack.review_trigger = {"status": "error", "error": str(e)}

        evidence_pack.collection_duration_seconds = time.time() - start_time
        return evidence_pack

    def _collect_environment_evidence(self, attempt: GateAttempt, evidence: EvidencePack) -> None:
        """收集环境证据"""
        try:
            # 获取 Git revision
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=attempt.workspace,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                evidence.revision = result.stdout.strip()

            # 获取工作区指纹（使用 git status 的哈希）
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=attempt.workspace,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                evidence.workspace_fingerprint = str(hash(result.stdout.strip()))

        except subprocess.TimeoutExpired:
            raise TimeoutError("git_operation", 10)
        except Exception as e:  # noqa: BLE001
            raise EvidenceCollectionError("environment", str(e))

    def _collect_fitness_evidence(self, attempt: GateAttempt, evidence: EvidencePack) -> None:
        """运行 Entrix fitness 检查"""
        policy = GovernancePolicy()
        preset = get_project_preset()
        report, dimensions = run_fitness_report(
            attempt.workspace,
            policy,
            preset,
            changed_files=attempt.changed_files,
            base=attempt.base_ref or "HEAD~1",
        )

        # 转换为证据格式
        evidence.fitness = {
            "status": "pass" if not report.hard_gate_blocked and not report.score_blocked else "fail",
            "final_score": report.final_score,
            "hard_gate_blocked": report.hard_gate_blocked,
            "score_blocked": report.score_blocked,
            "metrics_count": sum(len(dim.results) for dim in dimensions),
            "failed_metrics": [
                {
                    "name": result.metric_name,
                    "severity": "hard_gate" if result.hard_gate else "soft_gate",
                    "output": result.output[:500],  # 限制输出长度
                }
                for dim in dimensions
                for result in dim.results
                if not result.passed
            ],
        }

    def _collect_review_trigger_evidence(self, attempt: GateAttempt, evidence: EvidencePack) -> None:
        """运行 review trigger 检查"""
        rules_file = attempt.workspace / "docs" / "fitness" / "review-triggers.yaml"
        if not rules_file.exists():
            evidence.review_trigger = {"status": "skipped", "reason": "无规则文件"}
            return

        rules = load_review_triggers(rules_file)
        base = attempt.base_ref or "HEAD~1"
        changed_files = collect_changed_files(attempt.workspace, base)
        diff_stats = collect_diff_stats(attempt.workspace, base)

        report = evaluate_review_triggers(
            rules, changed_files, diff_stats, base=base, repo_root=attempt.workspace
        )

        evidence.review_trigger = {
            "status": "pass" if not report.human_review_required else "fail",
            "human_review_required": report.human_review_required,
            "triggers": [
                {
                    "name": trigger.name,
                    "severity": trigger.severity,
                }
                for trigger in report.triggers
            ],
        }
