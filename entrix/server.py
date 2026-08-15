"""MCP server —— 将 guardrail 检查作为工具暴露给 AI agent 集成。"""

from __future__ import annotations

from pathlib import Path


def create_server(project_root: Path | None = None):
    """创建并配置 FastMCP server。

    需要 [mcp] 可选依赖：pip install entrix[mcp]
    """
    try:
        from fastmcp import FastMCP
    except ImportError as e:
        raise ImportError(
            "fastmcp is not installed. Install with: pip install entrix[mcp]"
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
        from entrix.engine import run_fitness_report
        from entrix.governance import GovernancePolicy
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

        report, _ = run_fitness_report(project_root, policy, get_project_preset())
        return report_to_dict(report)

    @mcp.tool()
    def get_dimension_status(dimension: str) -> dict:
        """获取特定 fitness dimension 的当前状态。

        Args:
            dimension: Dimension 名称（例如 'code_quality'、'security'）。
        """
        from entrix.engine import run_fitness_report
        from entrix.governance import GovernancePolicy
        from entrix.presets import get_project_preset

        report, _ = run_fitness_report(
            project_root,
            GovernancePolicy(),
            get_project_preset(),
        )

        for ds in report.dimensions:
            if ds.dimension == dimension:
                return {
                    "final_score": report.final_score,
                    "name": ds.dimension,
                    "weight": ds.weight,
                    "score": ds.score,
                    "passed": ds.passed,
                    "total": ds.total,
                    "hard_gate_failures": ds.hard_gate_failures,
                    "results": [
                        {
                            "name": r.metric_name,
                            "passed": r.passed,
                            "state": r.state.value if r.state else None,
                            "tier": r.tier.value,
                            "hard_gate": r.hard_gate,
                        }
                        for r in ds.results
                    ],
                }

        return {"error": f"Dimension '{dimension}' not found"}

    @mcp.tool()
    def analyze_change_impact(
        changed_files: list[str] | None = None,
        depth: int = 2,
        base: str = "HEAD",
    ) -> dict:
        """使用 code graph 分析变更的 blast radius。

        需要可用的 graph backend。

        Args:
            changed_files: 显式文件列表，或 None 以通过 git 自动检测。
            depth: 影响分析的 BFS 遍历深度。
            base: 用于 diff 的 Git ref。
        """
        from entrix.runners.graph import GraphRunner

        runner = GraphRunner(project_root)
        if not runner.available:
            return {"status": "unavailable", "reason": "graph backend unavailable"}

        result = runner.probe_impact(base=base, max_depth=depth)
        return {
            "status": "ok",
            "passed": result.passed,
            "output": result.output,
        }

    return mcp


def main() -> None:
    """`entrix serve` 的入口点。"""
    server = create_server()
    server.run(transport="stdio")
