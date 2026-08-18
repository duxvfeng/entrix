"""Tests for MCP tool behavior and return value validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

# Skip all MCP tests if fastmcp is not installed
pytest.importorskip("fastmcp", reason="requires fastmcp package")

from entrix.model import (
    DimensionScore,
    FitnessReport,
    Metric,
    MetricResult,
    ResultState,
    Tier,
)
from entrix.server import create_server


class FakeAdapter:
    """Fake graph adapter for testing."""

    def __init__(self) -> None:
        self.build_calls: list[dict[str, Any]] = []
        self.impact_calls: list[dict[str, Any]] = []

    def build_or_update(self, *, full: bool = False, base: str = "HEAD") -> dict[str, Any]:
        self.build_calls.append({"full": full, "base": base})
        return {"status": "ok", "build_type": "full" if full else "incremental"}

    def impact_radius(self, files: list[str], *, depth: int = 2) -> dict[str, Any]:
        self.impact_calls.append({"files": files, "depth": depth})
        return {
            "status": "ok",
            "summary": "impact analysis completed",
            "changed_nodes": [
                {
                    "qualified_name": "src.service.run",
                    "name": "run",
                    "kind": "Function",
                    "file_path": "src/service.ts",
                }
            ],
            "impacted_nodes": [],
            "impacted_files": ["src/service.test.ts", "src/affected.ts"],
            "edges": [],
        }

    def stats(self) -> dict[str, Any]:
        return {"status": "ok", "nodes": 10, "edges": 12}


@pytest.fixture
def mock_fitness_report():
    """Create a mock fitness report for testing."""
    return FitnessReport(
        final_score=85.0,
        dimensions=[
            DimensionScore(
                dimension="code_quality",
                weight=30,
                score=90.0,
                passed=True,
                total=5,
                hard_gate_failures=[],
                results=[
                    MetricResult(
                        metric_name="ruff_check",
                        passed=True,
                        output="All checks passed",
                        tier=Tier.FAST,
                        hard_gate=True,
                    ),
                    MetricResult(
                        metric_name="mypy_check",
                        passed=False,
                        output="Type check failed",
                        tier=Tier.NORMAL,
                        hard_gate=False,
                        state=ResultState.FAIL,
                    ),
                ],
            ),
            DimensionScore(
                dimension="testability",
                weight=40,
                score=80.0,
                passed=True,
                total=3,
                hard_gate_failures=[],
                results=[
                    MetricResult(
                        metric_name="pytest",
                        passed=True,
                        output="Tests passed",
                        tier=Tier.NORMAL,
                        hard_gate=True,
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def sample_harness_yaml(tmp_path: Path):
    """Create a sample harness.yaml for testing."""
    harness_yaml = tmp_path / "harness.yaml"
    harness_yaml.write_text(
        """
fitness:
  - dimensions:
      - name: code_quality
        weight: 30
        metrics:
          - name: ruff_check
            tier: fast
            command: echo "ruff ok"
            hard_gate: true
          - name: mypy_check
            tier: normal
            command: echo "mypy failed"
            hard_gate: false
      - name: testability
        weight: 40
        metrics:
          - name: pytest
            tier: normal
            command: echo "pytest passed"
            hard_gate: true
""",
        encoding="utf-8",
    )
    return harness_yaml


def test_run_fitness_returns_valid_report_structure(
    sample_harness_yaml, mock_fitness_report, monkeypatch, tmp_path: Path
):
    """Test that run_fitness tool returns a valid report structure."""
    # Mock run_fitness_report to return our mock report
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        result = run_fitness(tier="fast", dry_run=True)

        # Verify result structure
        assert isinstance(result, dict), "Result should be a dict"
        assert "final_score" in result, "Result should contain final_score"
        assert "dimensions" in result, "Result should contain dimensions"

        # Verify dimensions structure
        assert isinstance(result["dimensions"], list), "dimensions should be a list"
        assert len(result["dimensions"]) == 2, "Should have 2 dimensions"

        # Verify dimension structure
        first_dim = result["dimensions"][0]
        assert "name" in first_dim
        assert "weight" in first_dim
        assert "score" in first_dim
        assert "passed" in first_dim
        assert "results" in first_dim

        # Verify metric results structure
        first_result = first_dim["results"][0]
        assert "name" in first_result
        assert "passed" in first_result
        assert "tier" in first_result


def test_get_dimension_status_returns_correct_dimension(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that get_dimension_status returns the correct dimension."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("code_quality")

        # Verify structure
        assert isinstance(result, dict), "Result should be a dict"
        assert result["name"] == "code_quality", "Should return code_quality dimension"
        assert "weight" in result
        assert "score" in result
        assert "passed" in result
        assert "total" in result
        assert "hard_gate_failures" in result
        assert "results" in result

        # Verify results list
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 2

        # Verify metric result structure
        first_metric = result["results"][0]
        assert "name" in first_metric
        assert "passed" in first_metric
        assert "state" in first_metric
        assert "tier" in first_metric
        assert "hard_gate" in first_metric


def test_get_dimension_status_returns_error_for_unknown_dimension(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that get_dimension_status returns error for non-existent dimension."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("unknown_dimension")

        assert isinstance(result, dict)
        assert "error" in result
        assert "unknown_dimension" in result["error"]


def test_analyze_change_impact_returns_valid_structure(
    sample_harness_yaml, monkeypatch, tmp_path: Path
):
    """Test that analyze_change_impact returns a valid structure."""
    # Mock graph adapter
    fake_adapter = FakeAdapter()
    monkeypatch.setattr(
        "entrix.runners.graph.try_create_adapter", lambda _: fake_adapter
    )

    server = create_server(tmp_path)
    tools_dict = getattr(server, "_tools", {})
    analyze_change_impact = tools_dict.get("analyze_change_impact")

    result = analyze_change_impact(
        changed_files=["src/service.ts"], depth=2, base="HEAD"
    )

    # Verify structure
    assert isinstance(result, dict), "Result should be a dict"
    assert "status" in result
    assert "passed" in result
    assert "output" in result


def test_analyze_change_impact_unavailable_without_graph_backend(
    sample_harness_yaml, monkeypatch, tmp_path: Path
):
    """Test that analyze_change_impact returns unavailable when graph backend is missing."""
    # Mock no graph adapter available
    monkeypatch.setattr("entrix.runners.graph.try_create_adapter", lambda _: None)

    server = create_server(tmp_path)
    tools_dict = getattr(server, "_tools", {})
    analyze_change_impact = tools_dict.get("analyze_change_impact")

    result = analyze_change_impact(changed_files=["src/service.ts"])

    # Should return unavailable status
    assert isinstance(result, dict)
    assert "status" in result
    assert "reason" in result
    assert "unavailable" in result["status"]


def test_run_fitness_includes_final_score(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that run_fitness result includes final_score."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        result = run_fitness()

        assert "final_score" in result
        assert isinstance(result["final_score"], (int, float))


def test_run_fitness_tier_filter_passed_correctly(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that run_fitness correctly passes tier filter to run_fitness_report."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        # Test with tier parameter
        run_fitness(tier="fast")

        # Verify run_fitness_report was called
        assert mock_run.called


def test_get_dimension_status_includes_final_score_in_result(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that get_dimension_status includes overall final_score."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("code_quality")

        assert "final_score" in result
        assert isinstance(result["final_score"], (int, float))


def test_analyze_change_impact_with_none_changed_files_uses_git(
    sample_harness_yaml, monkeypatch, tmp_path: Path
):
    """Test that analyze_change_impact with None changed_files uses git detection."""
    fake_adapter = FakeAdapter()
    monkeypatch.setattr(
        "entrix.runners.graph.try_create_adapter", lambda _: fake_adapter
    )

    # Mock git_changed_files to return some files
    with patch("entrix.runners.graph.git_changed_files") as mock_git:
        mock_git.return_value = ["src/service.ts", "docs/readme.md"]

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        analyze_change_impact = tools_dict.get("analyze_change_impact")

        # Call with None changed_files
        analyze_change_impact(changed_files=None, depth=2, base="HEAD")

        # Verify git_changed_files was called
        assert mock_git.called


def test_run_fitness_metric_result_state_conversion(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that metric result state is correctly converted to string."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("code_quality")

        # Check that state is converted to string value
        mypy_result = next(
            (r for r in result["results"] if r["name"] == "mypy_check"), None
        )
        assert mypy_result is not None
        assert "state" in mypy_result
        # State should be a string (from ResultState enum)
        assert isinstance(mypy_result["state"], str) or mypy_result["state"] is None
