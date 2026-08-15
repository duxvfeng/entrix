"""fitness report 的共享序列化辅助函数。"""

from __future__ import annotations

import json
from pathlib import Path

from entrix.model import FitnessReport


def report_to_dict(report: FitnessReport) -> dict:
    """将 fitness report 序列化为稳定的 JSON 友好结构。"""
    return {
        "final_score": report.final_score,
        "hard_gate_blocked": report.hard_gate_blocked,
        "score_blocked": report.score_blocked,
        "dimensions": [
            {
                "name": ds.dimension,
                "weight": ds.weight,
                "score": ds.score,
                "passed": ds.passed,
                "total": ds.total,
                "hard_gate_failures": ds.hard_gate_failures,
                "results": [
                    {
                        "name": result.metric_name,
                        "passed": result.passed,
                        "state": result.state.value if result.state else None,
                        "tier": result.tier.value,
                        "hard_gate": result.hard_gate,
                        "duration_ms": result.duration_ms,
                        "output": result.output,
                    }
                    for result in ds.results
                ],
            }
            for ds in report.dimensions
        ],
    }


def write_report_output(path: str | None, payload: dict) -> None:
    """将 JSON payload 写入文件路径或 stdout 标记。"""
    if not path:
        return
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    if path == "-":
        print(serialized)
        return
    Path(path).write_text(serialized + "\n", encoding="utf-8")
