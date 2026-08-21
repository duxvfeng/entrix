"""Runtime fitness event and artifact persistence for the CLI."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from entrix.model import FitnessReport


def runtime_marker(project_root: Path) -> str:
    return hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()


def runtime_root(project_root: Path) -> Path:
    return (
        Path(tempfile.gettempdir()) / "harness-monitor" / "runtime" / runtime_marker(project_root)
    )


def runtime_event_path(project_root: Path) -> Path:
    return runtime_root(project_root) / "events.jsonl"


def runtime_fitness_artifact_dir(project_root: Path) -> Path:
    return runtime_root(project_root) / "artifacts" / "fitness"


def runtime_fitness_mailbox_dir(project_root: Path) -> Path:
    return runtime_root(project_root) / "mailbox" / "fitness" / "new"


def _runtime_dir(
    project_root: Path,
    runtime_root_resolver: Callable[[Path], Path] | None,
) -> Path:
    return (runtime_root if runtime_root_resolver is None else runtime_root_resolver)(project_root)


def runtime_mode(tier: str | None) -> str:
    if tier is None or tier == "" or tier == "normal":
        return "full"
    return tier


def load_runtime_coverage_summary(project_root: Path) -> dict:
    summary_path = project_root / "target" / "coverage" / "fitness-summary.json"
    if not summary_path.is_file():
        return {"generated_at_ms": None, "typescript": {}, "rust": {}}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"generated_at_ms": None, "typescript": {}, "rust": {}}
    sources = payload.get("sources", {})
    return {
        "generated_at_ms": payload.get("generated_at_ms"),
        "typescript": sources.get("typescript", {}) or {},
        "rust": sources.get("rust", {}) or {},
    }


def summarize_metric_output(output: str) -> str | None:
    lines = [line.strip() for line in output.splitlines() if line.strip()][:3]
    if not lines:
        return None
    excerpt = " | ".join(lines)
    if len(excerpt) > 180:
        excerpt = excerpt[:177] + "..."
    return excerpt


def build_runtime_fitness_snapshot(
    project_root: Path,
    *,
    tier: str | None,
    report: FitnessReport,
    duration_ms: float,
    artifact_path: str,
    observed_at_ms: int,
    producer: str,
    base_ref: str | None,
    changed_files: list[str],
) -> dict:
    dimensions = []
    slowest_metrics = []
    failing_metrics = []
    coverage_metric_available = False

    for dimension_score in report.dimensions:
        metrics = []
        for result in dimension_score.results:
            metric_summary = {
                "name": result.metric_name,
                "passed": result.passed,
                "state": result.state.value if result.state is not None else "unknown",
                "hard_gate": result.hard_gate,
                "duration_ms": result.duration_ms,
                "output_excerpt": summarize_metric_output(result.output),
            }
            metrics.append(metric_summary)
            slowest_metrics.append(metric_summary)
            if metric_summary["state"] not in ("pass", "waived"):
                failing_metrics.append(metric_summary)
            coverage_metric_available = coverage_metric_available or (
                "coverage" in result.metric_name.lower() or "cover" in result.metric_name.lower()
            )
        dimensions.append(
            {
                "name": dimension_score.dimension,
                "weight": dimension_score.weight,
                "score": dimension_score.score,
                "passed": dimension_score.passed,
                "total": dimension_score.total,
                "hard_gate_failures": dimension_score.hard_gate_failures,
                "metrics": metrics,
            }
        )

    slowest_metrics.sort(key=lambda metric: metric["duration_ms"], reverse=True)
    failing_metrics.sort(
        key=lambda metric: (
            not metric["hard_gate"],
            -metric["duration_ms"],
            metric["name"],
        )
    )
    return {
        "mode": runtime_mode(tier),
        "final_score": report.final_score,
        "hard_gate_blocked": report.hard_gate_blocked,
        "score_blocked": report.score_blocked,
        "duration_ms": duration_ms,
        "metric_count": sum(len(ds.results) for ds in report.dimensions),
        "coverage_metric_available": coverage_metric_available,
        "coverage_summary": load_runtime_coverage_summary(project_root),
        "dimensions": dimensions,
        "slowest_metrics": slowest_metrics[:5],
        "artifact_path": artifact_path,
        "producer": producer,
        "generated_at_ms": observed_at_ms,
        "base_ref": base_ref,
        "changed_file_count": len(changed_files),
        "changed_files_preview": changed_files[:8],
        "failing_metrics": failing_metrics[:5],
    }


def write_runtime_fitness_artifacts(
    project_root: Path,
    *,
    tier: str | None,
    snapshot: dict,
    observed_at_ms: int,
    runtime_root_resolver: Callable[[Path], Path] | None = None,
) -> str:
    mode = runtime_mode(tier)
    artifact_dir = _runtime_dir(project_root, runtime_root_resolver) / "artifacts" / "fitness"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{observed_at_ms}-{mode}.json"
    latest_path = artifact_dir / f"latest-{mode}.json"
    serialized = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    artifact_path.write_text(serialized, encoding="utf-8")
    latest_path.write_text(serialized, encoding="utf-8")
    return str(artifact_path)


def write_runtime_fitness_mailbox_message(
    project_root: Path,
    *,
    payload: dict,
    runtime_root_resolver: Callable[[Path], Path] | None = None,
) -> None:
    mailbox_dir = _runtime_dir(project_root, runtime_root_resolver) / "mailbox" / "fitness" / "new"
    mailbox_dir.mkdir(parents=True, exist_ok=True)
    mailbox_path = mailbox_dir / f"{payload['observed_at_ms']}-{payload['mode']}.json"
    mailbox_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def emit_runtime_fitness_event(
    project_root: Path,
    *,
    status: str,
    tier: str | None,
    report: FitnessReport | None,
    metric_count: int | None,
    duration_ms: float | None,
    artifact_path: str | None,
    runtime_root_resolver: Callable[[Path], Path] | None = None,
) -> None:
    mode = runtime_mode(tier)
    event_path = _runtime_dir(project_root, runtime_root_resolver) / "events.jsonl"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "fitness",
        "repo_root": str(project_root),
        "observed_at_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "mode": mode,
        "status": status,
        "final_score": None if report is None else report.final_score,
        "hard_gate_blocked": None if report is None else report.hard_gate_blocked,
        "score_blocked": None if report is None else report.score_blocked,
        "duration_ms": duration_ms,
        "dimension_count": None if report is None else len(report.dimensions),
        "metric_count": metric_count,
        "artifact_path": artifact_path,
    }
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True))
        handle.write("\n")
    write_runtime_fitness_mailbox_message(
        project_root,
        payload=payload,
        runtime_root_resolver=runtime_root_resolver,
    )
