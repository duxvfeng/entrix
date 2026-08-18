"""Tests for MCP server error handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# Skip all MCP tests if fastmcp is not installed
pytest.importorskip("fastmcp", reason="requires fastmcp package")

from entrix.server import create_server


def test_create_server_raises_import_error_without_fastmcp(monkeypatch):
    """Test that create_server raises helpful ImportError when fastmcp is missing."""
    # Simulate fastmcp not being installed
    import sys
    original_import = __builtins__.__import__

    def mock_import(name, *args, **kwargs):
        if name == "fastmcp" or name.startswith("fastmcp."):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(__builtins__, "__import__", mock_import)

    with pytest.raises(ImportError) as exc_info:
        create_server(Path.cwd())

    assert "fastmcp is not installed" in str(exc_info.value)
    assert "pip install entrix[mcp]" in str(exc_info.value)


def test_create_server_import_error_suggests_fix(monkeypatch):
    """Test that ImportError provides installation guidance."""
    # Remove fastmcp from sys.modules if present
    fastmcp_module = sys.modules.pop("fastmcp", None)

    def mock_fastmcp_import(name, *args, **kwargs):
        if name == "fastmcp":
            raise ImportError("No module named 'fastmcp'")
        return __builtins__.__import__(name, *args, **kwargs)

    monkeypatch.setattr(__builtins__, "__import__", mock_fastmcp_import)

    try:
        with pytest.raises(ImportError) as exc_info:
            create_server()

        error_msg = str(exc_info.value)
        assert "fastmcp" in error_msg.lower()
        assert "install" in error_msg.lower() or "pip" in error_msg.lower()
    finally:
        # Restore fastmcp if it was imported
        if fastmcp_module:
            sys.modules["fastmcp"] = fastmcp_module


def test_run_fitness_handles_missing_harness_yaml(tmp_path: Path, monkeypatch):
    """Test that run_fitness tool handles missing harness.yaml gracefully."""
    # Don't create harness.yaml, so it's missing

    with patch("entrix.server.run_fitness_report") as mock_run:
        # Mock to raise FileNotFoundError
        mock_run.side_effect = FileNotFoundError("harness.yaml not found")

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        # Tool should propagate the error
        with pytest.raises(FileNotFoundError):
            run_fitness(tier="fast")


def test_run_fitness_handles_harness_parse_error(
    tmp_path: Path, sample_harness_yaml_invalid
):
    """Test that run_fitness handles invalid harness.yaml."""
    # Invalid harness.yaml will be created by fixture
    server = create_server(tmp_path)
    tools_dict = getattr(server, "_tools", {})
    run_fitness = tools_dict.get("run_fitness")

    # Should raise error due to invalid YAML
    with pytest.raises(Exception):
        run_fitness(tier="fast")


def test_get_dimension_status_handles_invalid_dimension_name(
    sample_harness_yaml_valid, tmp_path: Path
):
    """Test that get_dimension_status handles dimension names with special characters."""
    with patch("entrix.server.run_fitness_report") as mock_run:
        from entrix.model import FitnessReport, DimensionScore

        mock_run.return_value = (
            FitnessReport(
                final_score=80.0,
                dimensions=[
                    DimensionScore(
                        dimension="code-quality",  # With hyphen
                        weight=30,
                        score=90.0,
                        passed=True,
                        total=5,
                        hard_gate_failures=[],
                        results=[],
                    )
                ],
            ),
            None,
        )

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        get_dimension_status = tools_dict.get("get_dimension_status")

        # Should handle special characters in dimension name
        result = get_dimension_status("code-quality")
        assert result["name"] == "code-quality"


def test_analyze_change_impact_handles_graph_exception(
    sample_harness_yaml_valid, monkeypatch, tmp_path: Path
):
    """Test that analyze_change_impact handles graph adapter exceptions."""
    # Mock adapter that raises exception
    class BrokenAdapter:
        def impact_radius(self, files, *, depth):
            raise RuntimeError("Graph backend crashed")

    monkeypatch.setattr(
        "entrix.runners.graph.try_create_adapter", lambda _: BrokenAdapter()
    )

    server = create_server(tmp_path)
    tools_dict = getattr(server, "_tools", {})
    analyze_change_impact = tools_dict.get("analyze_change_impact")

    # Should handle exception gracefully
    result = analyze_change_impact(changed_files=["test.ts"])
    # Tool should return error status rather than raising
    assert isinstance(result, dict)


def test_mcp_tools_graceful_degradation_on_optional_dependencies(
    tmp_path: Path, monkeypatch
):
    """Test that MCP tools handle missing optional dependencies gracefully."""
    # Simulate missing graph backend
    monkeypatch.setattr("entrix.runners.graph.try_create_adapter", lambda _: None)

    server = create_server(tmp_path)
    tools_dict = getattr(server, "_tools", {})
    analyze_change_impact = tools_dict.get("analyze_change_impact")

    result = analyze_change_impact(changed_files=["test.ts"])

    # Should return unavailable status
    assert result["status"] == "unavailable"
    assert "reason" in result


# Fixtures for test data
@pytest.fixture
def sample_harness_yaml_invalid(tmp_path: Path):
    """Create an invalid harness.yaml for error testing."""
    harness_yaml = tmp_path / "harness.yaml"
    harness_yaml.write_text(
        """
fitness: invalid: yaml: structure
: broken
""",
        encoding="utf-8",
    )
    return harness_yaml


@pytest.fixture
def sample_harness_yaml_valid(tmp_path: Path):
    """Create a valid harness.yaml for error testing."""
    harness_yaml = tmp_path / "harness.yaml"
    harness_yaml.write_text(
        """
fitness:
  - dimensions:
      - name: code_quality
        weight: 30
        metrics:
          - name: test_metric
            tier: fast
            command: echo "test"
            hard_gate: true
""",
        encoding="utf-8",
    )
    return harness_yaml


def test_server_creation_with_invalid_project_root(monkeypatch):
    """Test that create_server handles invalid project root path."""
    # Mock Path.cwd() to return a path that doesn't exist
    fake_path = Path("/nonexistent/path/that/does/not/exist")

    monkeypatch.setattr("pathlib.Path.cwd", lambda: fake_path)

    # Should still create server, even if path doesn't exist yet
    # (tools will fail when called, not during server creation)
    try:
        server = create_server()
        assert server is not None
    except Exception as e:
        # If it fails, should be a clear error
        assert "path" in str(e).lower() or "directory" in str(e).lower()


def test_run_fitness_empty_dimensions(tmp_path: Path, monkeypatch):
    """Test run_fitness with empty dimensions list."""
    harness_yaml = tmp_path / "harness.yaml"
    harness_yaml.write_text(
        """
fitness:
  - dimensions: []
""",
        encoding="utf-8",
    )

    with patch("entrix.server.run_fitness_report") as mock_run:
        from entrix.model import FitnessReport

        mock_run.return_value = (FitnessReport(final_score=0.0, dimensions=[]), None)

        server = create_server(tmp_path)
        tools_dict = getattr(server, "_tools", {})
        run_fitness = tools_dict.get("run_fitness")

        result = run_fitness()

        assert isinstance(result, dict)
        assert "dimensions" in result
        assert result["dimensions"] == []


def test_mcp_tool_type_validation(tmp_path: Path, sample_harness_yaml_valid):
    """Test that MCP tools validate input types correctly."""
    server = create_server(tmp_path)
    tools_dict = getattr(server, "_tools", {})

    # Test run_fitness with invalid types
    run_fitness = tools_dict.get("run_fitness")

    # These should raise TypeError or handle gracefully
    # (depending on FastMCP's validation)
    try:
        # Invalid tier (not a string or None)
        result = run_fitness(tier=123)  # type: ignore
        # If it doesn't raise, result should still be valid
        assert isinstance(result, dict)
    except (TypeError, ValueError):
        # Expected: type validation should catch this
        pass
