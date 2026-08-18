"""Tests for MCP tool return value format validation and JSON schema compliance."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import json
import pytest

# Skip all MCP tests if fastmcp is not installed
pytest.importorskip("fastmcp", reason="requires fastmcp package")

from entrix.model import (
    DimensionScore,
    FitnessReport,
    MetricResult,
    ResultState,
    Tier,
)
from entrix.server import create_server


@pytest.fixture
def mock_fitness_report():
    """Create a comprehensive mock fitness report for format validation."""
    return FitnessReport(
        final_score=85.5,
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
                        output="All checks passed\nNo issues found",
                        tier=Tier.FAST,
                        hard_gate=True,
                    ),
                    MetricResult(
                        metric_name="mypy_check",
                        passed=False,
                        output="Found 2 type errors",
                        tier=Tier.NORMAL,
                        hard_gate=False,
                        state=ResultState.FAIL,
                    ),
                    MetricResult(
                        metric_name="bandit_check",
                        passed=True,
                        output="Security checks passed",
                        tier=Tier.DEEP,
                        hard_gate=True,
                        state=ResultState.PASS,
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
                        output="15 passed, 0 failed",
                        tier=Tier.NORMAL,
                        hard_gate=True,
                    ),
                    MetricResult(
                        metric_name="coverage",
                        passed=True,
                        output="Coverage: 85%",
                        tier=Tier.NORMAL,
                        hard_gate=False,
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def sample_harness_yaml(tmp_path: Path):
    """Create a comprehensive harness.yaml for testing."""
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
          - name: bandit_check
            tier: deep
            command: echo "security ok"
            hard_gate: true
      - name: testability
        weight: 40
        metrics:
          - name: pytest
            tier: normal
            command: echo "pytest passed"
            hard_gate: true
          - name: coverage
            tier: normal
            command: echo "coverage 85%"
            hard_gate: false
""",
        encoding="utf-8",
    )
    return harness_yaml


def test_run_fitness_return_value_is_json_serializable(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that run_fitness return value can be serialized to JSON."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        result = run_fitness(tier="fast")

        # Should be JSON serializable
        try:
            json_str = json.dumps(result)
            assert isinstance(json_str, str)
        except (TypeError, ValueError) as e:
            pytest.fail(f"Result is not JSON serializable: {e}")


def test_run_fitness_return_value_schema_validation(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that run_fitness return value matches expected schema."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        result = run_fitness()

        # Top-level structure
        assert isinstance(result, dict)
        assert set(result.keys()) >= {"final_score", "dimensions"}

        # final_score validation
        assert isinstance(result["final_score"], (int, float))

        # dimensions validation
        assert isinstance(result["dimensions"], list)
        assert len(result["dimensions"]) > 0

        for dim in result["dimensions"]:
            # Dimension structure
            assert isinstance(dim, dict)
            required_dim_keys = {"name", "weight", "score", "passed", "total", "results"}
            assert set(dim.keys()) >= required_dim_keys

            assert isinstance(dim["name"], str)
            assert isinstance(dim["weight"], (int, float))
            assert isinstance(dim["score"], (int, float))
            assert isinstance(dim["passed"], bool)
            assert isinstance(dim["total"], int)

            # Results validation
            assert isinstance(dim["results"], list)

            for metric in dim["results"]:
                assert isinstance(metric, dict)
                required_metric_keys = {"name", "passed", "tier"}
                assert set(metric.keys()) >= required_metric_keys

                assert isinstance(metric["name"], str)
                assert isinstance(metric["passed"], bool)
                assert isinstance(metric["tier"], str)

                # Optional fields
                if "state" in metric:
                    assert metric["state"] is None or isinstance(metric["state"], str)
                if "hard_gate" in metric:
                    assert isinstance(metric["hard_gate"], bool)


def test_get_dimension_status_return_value_schema(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that get_dimension_status return value matches expected schema."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("code_quality")

        # Top-level structure
        assert isinstance(result, dict)
        required_keys = {
            "final_score",
            "name",
            "weight",
            "score",
            "passed",
            "total",
            "hard_gate_failures",
            "results",
        }
        assert set(result.keys()) == required_keys

        # Field types
        assert isinstance(result["final_score"], (int, float))
        assert isinstance(result["name"], str)
        assert isinstance(result["weight"], (int, float))
        assert isinstance(result["score"], (int, float))
        assert isinstance(result["passed"], bool)
        assert isinstance(result["total"], int)
        assert isinstance(result["hard_gate_failures"], int)
        assert isinstance(result["results"], list)


def test_get_dimension_status_metric_results_schema(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that metric results in get_dimension_status match schema."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("code_quality")

        # Check each metric result
        for metric in result["results"]:
            assert isinstance(metric, dict)
            required_keys = {"name", "passed", "state", "tier", "hard_gate"}
            assert set(metric.keys()) == required_keys

            assert isinstance(metric["name"], str)
            assert isinstance(metric["passed"], bool)
            assert isinstance(metric["tier"], str)
            assert isinstance(metric["hard_gate"], bool)

            # state can be null or string
            assert metric["state"] is None or isinstance(metric["state"], str)


def test_analyze_change_impact_return_value_schema(
    sample_harness_yaml, monkeypatch, tmp_path: Path
):
    """Test that analyze_change_impact return value matches expected schema."""
    from entrix.runners.graph import GraphRunner

    # Mock successful impact analysis
    class FakeAdapter:
        def build_or_update(self, *, full: bool = False, base: str = "HEAD"):
            return {"status": "ok", "build_type": "incremental"}

        def impact_radius(self, files, *, depth: int = 2):
            return {
                "status": "ok",
                "summary": "Analysis completed",
                "changed_nodes": [],
                "impacted_nodes": [],
                "impacted_files": ["src/test.ts"],
                "edges": [],
            }

        def stats(self):
            return {"status": "ok", "nodes": 5, "edges": 8}

    monkeypatch.setattr("entrix.runners.graph.try_create_adapter", lambda _: FakeAdapter())

    server = create_server(tmp_path)
    tools_dict = getattr(server, "_tools", {})
    analyze_change_impact = tools_dict.get("analyze_change_impact")

    result = analyze_change_impact(changed_files=["src/service.ts"])

    # Structure validation
    assert isinstance(result, dict)
    required_keys = {"status", "passed", "output"}
    assert set(result.keys()) >= required_keys

    assert isinstance(result["status"], str)
    assert isinstance(result["passed"], bool)
    assert isinstance(result["output"], str)


def test_analyze_change_impact_unavailable_schema(
    sample_harness_yaml, monkeypatch, tmp_path: Path
):
    """Test that analyze_change_impact unavailable result matches schema."""
    # Mock no graph backend
    monkeypatch.setattr("entrix.runners.graph.try_create_adapter", lambda _: None)

    server = create_server(tmp_path)
    tools_dict = getattr(server, "_tools", {})
    analyze_change_impact = tools_dict.get("analyze_change_impact")

    result = analyze_change_impact(changed_files=["src/service.ts"])

    # Unavailable status structure
    assert isinstance(result, dict)
    assert "status" in result
    assert "reason" in result
    assert result["status"] == "unavailable"
    assert isinstance(result["reason"], str)


def test_all_tool_return_values_consistent_json_types(
    sample_harness_yaml, mock_fitness_report, monkeypatch, tmp_path: Path
):
    """Test that all MCP tools return JSON-compatible types."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        # Mock graph adapter
        class FakeAdapter:
            def build_or_update(self, *, full: bool = False, base: str = "HEAD"):
                return {"status": "ok"}

            def impact_radius(self, files, *, depth: int = 2):
                return {
                    "status": "ok",
                    "summary": "ok",
                    "changed_nodes": [],
                    "impacted_nodes": [],
                    "impacted_files": [],
                    "edges": [],
                }

            def stats(self):
                return {"status": "ok"}

        monkeypatch.setattr(
            "entrix.runners.graph.try_create_adapter", lambda _: FakeAdapter()
        )

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})

        # Test run_fitness
        run_fitness = tools_dict.get("run_fitness")
        fitness_result = run_fitness()
        _validate_json_types(fitness_result)

        # Test get_dimension_status
        get_dimension_status = tools_dict.get("get_dimension_status")
        dimension_result = get_dimension_status("code_quality")
        _validate_json_types(dimension_result)

        # Test analyze_change_impact
        analyze_change_impact = tools_dict.get("analyze_change_impact")
        impact_result = analyze_change_impact(changed_files=["test.ts"])
        _validate_json_types(impact_result)


def _validate_json_types(obj, max_depth=10):
    """Recursively validate that obj contains only JSON-serializable types."""
    if max_depth <= 0:
        return

    if isinstance(obj, dict):
        for v in obj.values():
            _validate_json_types(v, max_depth - 1)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _validate_json_types(item, max_depth - 1)
    elif not isinstance(obj, (str, int, float, bool, type(None))):
        pytest.fail(f"Non-JSON type found: {type(obj)}")


def test_metric_result_state_enum_conversion(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that ResultState enum is correctly converted to string."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("code_quality")

        # Find metrics with state
        for metric in result["results"]:
            if metric["state"] is not None:
                # State should be string value from enum
                assert isinstance(metric["state"], str)
                # Should match known ResultState values
                valid_states = {s.value for s in ResultState}
                assert metric["state"] in valid_states


def test_tier_enum_conversion_to_string(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that Tier enum is correctly converted to string."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("code_quality")

        # Check tier values
        for metric in result["results"]:
            assert isinstance(metric["tier"], str)
            # Should match known Tier values
            valid_tiers = {t.value for t in Tier}
            assert metric["tier"] in valid_tiers


def test_numeric_types_are_native_python_types(
    sample_harness_yaml, mock_fitness_report, tmp_path: Path
):
    """Test that numeric fields use native Python types (int/float), not numpy or decimal."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        mock_run.return_value = (mock_fitness_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        result = run_fitness()

        # Check final_score
        assert type(result["final_score"]) in (int, float)

        # Check dimension scores and weights
        for dim in result["dimensions"]:
            assert type(dim["weight"]) in (int, float)
            assert type(dim["score"]) in (int, float)
            assert type(dim["total"]) is int


def test_empty_results_list_handling(
    sample_harness_yaml, tmp_path: Path
):
    """Test that tools handle empty results gracefully."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        from entrix.model import FitnessReport

        empty_report = FitnessReport(final_score=0.0, dimensions=[])
        mock_run.return_value = (empty_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        result = run_fitness()

        # Should handle empty dimensions
        assert isinstance(result, dict)
        assert "dimensions" in result
        assert isinstance(result["dimensions"], list)
        assert len(result["dimensions"]) == 0


def test_dimension_not_found_error_structure(tmp_path: Path, sample_harness_yaml):
    """Test that dimension not found error has consistent structure."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        from entrix.model import FitnessReport

        mock_report = FitnessReport(
            final_score=80.0,
            dimensions=[
                DimensionScore(
                    dimension="existing_dimension",
                    weight=50,
                    score=90.0,
                    passed=True,
                    total=1,
                    hard_gate_failures=[],
                    results=[],
                )
            ],
        )
        mock_run.return_value = (mock_report, None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        result = get_dimension_status("nonexistent_dimension")

        # Should be a dict with error key
        assert isinstance(result, dict)
        assert "error" in result
        assert isinstance(result["error"], str)
        assert "nonexistent_dimension" in result["error"]
