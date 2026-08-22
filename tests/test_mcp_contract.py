from __future__ import annotations

import json
from pathlib import Path

import pytest

from entrix.model import DimensionScore, FitnessReport, MetricResult, ResultState, Tier
from entrix.server import (
    analyze_change_impact_tool,
    get_dimension_status_tool,
    run_fitness_tool,
)


def _report() -> FitnessReport:
    return FitnessReport(
        final_score=91.5,
        dimensions=[
            DimensionScore(
                dimension="code_quality",
                weight=100,
                passed=1,
                total=1,
                score=100.0,
                results=[
                    MetricResult(
                        metric_name="ruff_pass",
                        passed=True,
                        output="ok",
                        tier=Tier.FAST,
                        hard_gate=True,
                        state=ResultState.PASS,
                    )
                ],
            )
        ],
    )


def test_run_fitness_tool_returns_json_contract(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    config_path = tmp_path / "harness.yaml"
    config_path.write_text("version: harness/v1\n", encoding="utf-8")
    monkeypatch.setattr(
        "entrix.server.StopGateStateStore.is_config_trusted",
        lambda _store, _workspace, _config: True,
    )

    def fake_run(repo_root, policy, preset, *, dimensions):
        calls.update(repo_root=repo_root, policy=policy, preset=preset, dimensions=dimensions)
        return _report(), dimensions

    monkeypatch.setattr("entrix.engine.run_fitness_report", fake_run)
    monkeypatch.setattr(
        "entrix.harness.config.load_harness_config",
        lambda _path: type("Config", (), {"fitness_dimensions": ["configured"]})(),
    )

    result = run_fitness_tool(tmp_path, tier="fast", scope="local", dry_run=True)

    assert result["final_score"] == 91.5
    assert result["dimensions"][0]["name"] == "code_quality"
    assert calls["repo_root"] == tmp_path
    assert calls["dimensions"] == ["configured"]
    assert calls["policy"].tier_filter is Tier.FAST
    json.dumps(result)


def test_run_fitness_tool_reads_nested_harness_config(monkeypatch, tmp_path: Path) -> None:
    nested = tmp_path / ".harness" / "harness.yaml"
    nested.parent.mkdir()
    nested.write_text("version: harness/v1\n", encoding="utf-8")
    monkeypatch.setattr(
        "entrix.server.StopGateStateStore.is_config_trusted",
        lambda _store, _workspace, _config: True,
    )
    calls: list[Path] = []

    def fake_load(path: Path):
        calls.append(path)
        return type("Config", (), {"fitness_dimensions": []})()

    monkeypatch.setattr("entrix.harness.config.load_harness_config", fake_load)
    monkeypatch.setattr("entrix.engine.run_fitness_report", lambda *args, **kwargs: (_report(), []))

    run_fitness_tool(tmp_path)

    assert calls == [nested]


def test_run_fitness_tool_blocks_untrusted_harness(tmp_path: Path) -> None:
    config_path = tmp_path / "harness.yaml"
    config_path.write_text("version: harness/v1\n", encoding="utf-8")

    result = run_fitness_tool(tmp_path)

    assert result["status"] == "blocked"
    assert "尚未信任" in result["error"]
    assert "trust --repo" in result["next_action"]


@pytest.mark.parametrize("field,value", [("tier", "invalid"), ("scope", "invalid")])
def test_run_fitness_tool_rejects_invalid_enums(tmp_path: Path, field: str, value: str) -> None:
    with pytest.raises(ValueError):
        run_fitness_tool(tmp_path, **{field: value})


def test_get_dimension_status_tool_returns_stable_schema(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
    monkeypatch.setattr(
        "entrix.server.StopGateStateStore.is_config_trusted",
        lambda _store, _workspace, _config: True,
    )
    monkeypatch.setattr("entrix.engine.run_fitness_report", lambda *_args, **_kwargs: (_report(), []))
    monkeypatch.setattr(
        "entrix.harness.config.load_harness_config",
        lambda _path: type("Config", (), {"fitness_dimensions": []})(),
    )

    result = get_dimension_status_tool(tmp_path, "code_quality")

    assert set(result) == {
        "final_score",
        "name",
        "weight",
        "score",
        "passed",
        "total",
        "hard_gate_failures",
        "results",
    }
    assert result["passed"] == 1
    assert result["results"][0]["state"] == "pass"
    assert get_dimension_status_tool(tmp_path, "missing") == {
        "error": "Dimension 'missing' not found"
    }
    json.dumps(result)


def test_analyze_change_impact_tool_delegates_to_graph_runner(
    monkeypatch, tmp_path: Path
) -> None:
    calls: dict[str, object] = {}

    class FakeGraphRunner:
        available = True

        def __init__(self, project_root: Path) -> None:
            calls["root"] = project_root

        def analyze_impact(self, **kwargs):
            calls.update(kwargs)
            return {"status": "ok", "impacted_files": ["entrix/cli.py"]}

    monkeypatch.setattr("entrix.runners.graph.GraphRunner", FakeGraphRunner)

    result = analyze_change_impact_tool(
        tmp_path,
        changed_files=["entrix/server.py"],
        depth=3,
        base="HEAD~1",
        build_mode="skip",
    )

    assert result["status"] == "ok"
    assert calls == {
        "root": tmp_path,
        "changed_files": ["entrix/server.py"],
        "base": "HEAD~1",
        "max_depth": 3,
        "build_mode": "skip",
    }


def test_analyze_change_impact_tool_handles_unavailable_and_invalid_input(
    monkeypatch, tmp_path: Path
) -> None:
    class UnavailableGraphRunner:
        available = False

        def __init__(self, _project_root: Path) -> None:
            pass

    monkeypatch.setattr("entrix.runners.graph.GraphRunner", UnavailableGraphRunner)
    assert analyze_change_impact_tool(tmp_path) == {
        "status": "unavailable",
        "reason": "graph backend unavailable",
    }
    with pytest.raises(ValueError, match="positive"):
        analyze_change_impact_tool(tmp_path, depth=0)
    with pytest.raises(ValueError, match="build_mode"):
        analyze_change_impact_tool(tmp_path, build_mode="invalid")
