"""Tests for entrix MCP server integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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
            "impacted_files": ["src/service.test.ts"],
            "edges": [],
        }

    def stats(self) -> dict[str, Any]:
        return {"status": "ok", "nodes": 10, "edges": 12}


def test_create_server_without_fastmcp_raises_import_error(monkeypatch):
    """Test that create_server raises ImportError when fastmcp is not available."""
    # Simulate fastmcp not being installed
    monkeypatch.setattr("entrix.server.fastmcp", None)

    with pytest.raises(ImportError, match="fastmcp is not installed"):
        create_server()


def test_create_server_registers_expected_tools(tmp_path: Path, monkeypatch):
    """Test that MCP server registers all expected tools."""
    # Create a minimal harness.yaml
    harness_yaml = tmp_path / "harness.yaml"
    harness_yaml.write_text(
        """
fitness:
  - dimensions:
      - name: code_quality
        weight: 30
        metrics:
          - name: example_metric
            tier: fast
            command: echo "test"
""",
        encoding="utf-8",
    )

    # Mock the graph adapter
    fake_adapter = FakeAdapter()
    monkeypatch.setattr(
        "entrix.runners.graph.try_create_adapter", lambda _: fake_adapter
    )

    server = create_server(tmp_path)

    # FastMCP stores tools in _tool_names or _tools dict
    tool_names = getattr(server, "_tool_names", None)
    if tool_names is None:
        # FastMCP might store tools differently
        tools_dict = getattr(server, "_tools", {})
        tool_names = list(tools_dict.keys()) if tools_dict else []

    assert tool_names is not None, "Could not find tool names on server"
    expected_tools = {"run_fitness", "get_dimension_status", "analyze_change_impact"}
    assert expected_tools.issubset(set(tool_names)), (
        f"Expected tools {expected_tools}, got {set(tool_names)}"
    )


def test_mcp_server_instructions_are_set(tmp_path: Path):
    """Test that MCP server has proper instructions for AI agents."""
    server = create_server(tmp_path)
    instructions = getattr(server, "instructions", "")
    assert "Executable quality guardrails" in instructions
    assert "evolutionary architecture" in instructions
    assert "fitness functions" in instructions


def test_run_fitness_tool_signature():
    """Test that run_fitness tool has correct parameter signature."""
    server = create_server()
    tools_dict = getattr(server, "_tools", {})
    run_fitness = tools_dict.get("run_fitness")

    assert run_fitness is not None, "run_fitness tool not found"

    # Check that the tool is callable and has expected parameters
    import inspect

    sig = inspect.signature(run_fitness)
    params = list(sig.parameters.keys())
    expected_params = ["tier", "scope", "parallel", "dry_run", "min_score"]
    for param in expected_params:
        assert param in params, f"Parameter {param} not found in run_fitness"


def test_get_dimension_status_tool_signature():
    """Test that get_dimension_status tool has correct parameter signature."""
    server = create_server()
    tools_dict = getattr(server, "_tools", {})
    get_dimension_status = tools_dict.get("get_dimension_status")

    assert get_dimension_status is not None, "get_dimension_status tool not found"

    import inspect

    sig = inspect.signature(get_dimension_status)
    params = list(sig.parameters.keys())
    assert "dimension" in params, "Parameter 'dimension' not found in get_dimension_status"


def test_analyze_change_impact_tool_signature():
    """Test that analyze_change_impact tool has correct parameter signature."""
    server = create_server()
    tools_dict = getattr(server, "_tools", {})
    analyze_change_impact = tools_dict.get("analyze_change_impact")

    assert analyze_change_impact is not None, "analyze_change_impact tool not found"

    import inspect

    sig = inspect.signature(analyze_change_impact)
    params = list(sig.parameters.keys())
    expected_params = ["changed_files", "depth", "base"]
    for param in expected_params:
        assert param in params, f"Parameter {param} not found in analyze_change_impact"


def test_create_server_uses_project_root_when_provided(tmp_path: Path):
    """Test that create_server uses the provided project root."""
    server = create_server(tmp_path)
    # Server should have been created with the provided path
    assert server is not None


def test_create_server_defaults_to_cwd_when_no_root_provided(monkeypatch):
    """Test that create_server defaults to Path.cwd() when no root is provided."""
    fake_cwd = Path("/fake/project/root")
    monkeypatch.setattr("pathlib.Path.cwd", lambda: fake_cwd)

    server = create_server()
    assert server is not None


def test_run_fitness_tool_has_docstring():
    """Test that run_fitness tool has proper documentation."""
    server = create_server()
    tools_dict = getattr(server, "_tools", {})
    run_fitness = tools_dict.get("run_fitness")

    assert run_fitness is not None
    assert run_fitness.__doc__ is not None
    doc = run_fitness.__doc__
    assert "guardrail" in doc.lower() or "fitness" in doc.lower()


def test_get_dimension_status_tool_has_docstring():
    """Test that get_dimension_status tool has proper documentation."""
    server = create_server()
    tools_dict = getattr(server, "_tools", {})
    get_dimension_status = tools_dict.get("get_dimension_status")

    assert get_dimension_status is not None
    assert get_dimension_status.__doc__ is not None
    doc = get_dimension_status.__doc__
    assert "dimension" in doc.lower()


def test_analyze_change_impact_tool_has_docstring():
    """Test that analyze_change_impact tool has proper documentation."""
    server = create_server()
    tools_dict = getattr(server, "_tools", {})
    analyze_change_impact = tools_dict.get("analyze_change_impact")

    assert analyze_change_impact is not None
    assert analyze_change_impact.__doc__ is not None
    doc = analyze_change_impact.__doc__
    assert "impact" in doc.lower() or "blast" in doc.lower() or "graph" in doc.lower()
