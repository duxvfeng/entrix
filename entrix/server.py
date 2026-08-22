"""MCP server —— 将 guardrail 检查作为工具暴露给 AI agent 集成。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from entrix.stop_gate.revalidation import StopGateStateStore


def _harness_config_path(project_root: Path) -> Path:
    """Resolve the same Harness locations used by the Stop Hook."""
    for candidate in (project_root / "harness.yaml", project_root / ".harness" / "harness.yaml"):
        if candidate.is_file():
            return candidate
    return project_root / "harness.yaml"


def _trusted_harness_or_error(project_root: Path, config_path: Path) -> dict[str, str] | None:
    """Prevent MCP tools from executing commands from an untrusted Harness."""
    if not config_path.is_file():
        return {
            "status": "blocked",
            "error": f"未找到 Harness 配置：{config_path}",
        }
    if StopGateStateStore().is_config_trusted(project_root, config_path):
        return None
    return {
        "status": "blocked",
        "error": "Harness 配置尚未信任，MCP 不会自动执行其中的命令。",
        "next_action": f"检查配置后运行：entrix trust --repo {project_root}",
    }


def run_fitness_tool(
    project_root: Path,
    *,
    tier: str | None = None,
    scope: str | None = None,
    parallel: bool = False,
    dry_run: bool = False,
    min_score: float = 80.0,
) -> dict[str, Any]:
    """Run guardrail checks and return a JSON-compatible fitness report."""
    from entrix.engine import run_fitness_report
    from entrix.governance import GovernancePolicy
    from entrix.harness.config import load_harness_config
    from entrix.model import ExecutionScope, Tier
    from entrix.presets import get_project_preset
    from entrix.reporting import report_to_dict

    tier_filter = Tier(tier) if tier else None
    execution_scope = ExecutionScope(scope) if scope else None
    policy = GovernancePolicy(
        tier_filter=tier_filter,
        parallel=parallel,
        dry_run=dry_run,
        min_score=min_score,
        execution_scope=execution_scope,
    )
    config_path = _harness_config_path(project_root)
    if not dry_run:
        trust_error = _trusted_harness_or_error(project_root, config_path)
        if trust_error is not None:
            return trust_error
    config = load_harness_config(config_path)
    report, _ = run_fitness_report(
        project_root,
        policy,
        get_project_preset(),
        dimensions=config.fitness_dimensions,
    )
    return report_to_dict(report)


def get_dimension_status_tool(project_root: Path, dimension: str) -> dict[str, Any]:
    """Run fitness checks and return one dimension's current status."""
    from entrix.engine import run_fitness_report
    from entrix.governance import GovernancePolicy
    from entrix.harness.config import load_harness_config
    from entrix.presets import get_project_preset

    config_path = _harness_config_path(project_root)
    trust_error = _trusted_harness_or_error(project_root, config_path)
    if trust_error is not None:
        return trust_error
    report, _ = run_fitness_report(
        project_root,
        GovernancePolicy(),
        get_project_preset(),
        dimensions=load_harness_config(config_path).fitness_dimensions,
    )
    for dimension_score in report.dimensions:
        if dimension_score.dimension == dimension:
            return {
                "final_score": report.final_score,
                "name": dimension_score.dimension,
                "weight": dimension_score.weight,
                "score": dimension_score.score,
                "passed": dimension_score.passed,
                "total": dimension_score.total,
                "hard_gate_failures": dimension_score.hard_gate_failures,
                "results": [
                    {
                        "name": result.metric_name,
                        "passed": result.passed,
                        "state": result.state.value if result.state else None,
                        "tier": result.tier.value,
                        "hard_gate": result.hard_gate,
                    }
                    for result in dimension_score.results
                ],
            }
    return {"error": f"Dimension '{dimension}' not found"}


def analyze_change_impact_tool(
    project_root: Path,
    *,
    changed_files: list[str] | None = None,
    depth: int = 2,
    base: str = "HEAD",
    build_mode: str = "auto",
) -> dict[str, Any]:
    """Analyze the code-graph blast radius for a set of changed files."""
    from entrix.runners.graph import GraphRunner

    if depth < 1:
        raise ValueError("depth must be a positive integer")
    if build_mode not in {"auto", "full", "skip"}:
        raise ValueError("build_mode must be one of: auto, full, skip")

    runner = GraphRunner(project_root)
    if not runner.available:
        return {"status": "unavailable", "reason": "graph backend unavailable"}
    return runner.analyze_impact(
        changed_files=changed_files,
        base=base,
        max_depth=depth,
        build_mode=build_mode,
    )


def create_server(project_root: Path | None = None):
    """创建并配置 FastMCP server。

    需要 [mcp] 可选依赖：pip install entrix[mcp]
    """
    try:
        from fastmcp import FastMCP
    except ImportError as e:
        raise ImportError(
            "未安装 fastmcp。请使用以下命令安装: pip install entrix[mcp]"
        ) from e

    if project_root is None:
        project_root = Path.cwd()

    mcp = FastMCP(
        "entrix",
        instructions=(
            "Executable quality guardrails powered by evolutionary architecture "
            "fitness functions"
        ),
    )

    @mcp.tool()
    def run_fitness(
        tier: str | None = None,
        scope: str | None = None,
        parallel: bool = False,
        dry_run: bool = False,
        min_score: float = 80.0,
    ) -> dict:
        """运行 guardrail 检查并返回结构化的 fitness report。

        Args:
            tier: 按 tier 过滤（fast、normal、deep）。None 表示全部运行。
            scope: 按执行范围过滤（local、ci、staging、prod_observation）。
            parallel: 并行运行 metric。
            dry_run: 显示将要运行的内容而不实际执行。
            min_score: 结果被视为阻塞前的最低加权分数。
        """
        return run_fitness_tool(
            project_root,
            tier=tier,
            scope=scope,
            parallel=parallel,
            dry_run=dry_run,
            min_score=min_score,
        )

    @mcp.tool()
    def get_dimension_status(dimension: str) -> dict:
        """获取特定 fitness dimension 的当前状态。

        Args:
            dimension: Dimension 名称（例如 'code_quality'、'security'）。
        """
        return get_dimension_status_tool(project_root, dimension)

    @mcp.tool()
    def analyze_change_impact(
        changed_files: list[str] | None = None,
        depth: int = 2,
        base: str = "HEAD",
        build_mode: str = "auto",
    ) -> dict:
        """使用 code graph 分析变更的 blast radius。

        需要可用的 graph backend。

        Args:
            changed_files: 显式文件列表，或 None 以通过 git 自动检测。
            depth: 影响分析的 BFS 遍历深度。
            base: 用于 diff 的 Git ref。
            build_mode: Graph 构建模式（auto、full、skip）。
        """
        return analyze_change_impact_tool(
            project_root,
            changed_files=changed_files,
            depth=depth,
            base=base,
            build_mode=build_mode,
        )

    return mcp


def main() -> None:
    """`entrix serve` 的入口点。"""
    server = create_server()
    server.run(transport="stdio")
