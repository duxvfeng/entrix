"""基于路径根与 domain 启发式推断的默认 preset。"""

from __future__ import annotations

from pathlib import Path

from entrix.model import Metric


class DefaultPreset:
    """基于常见 monorepo 布局启发式推断 domain 的默认 preset。

    历史上仅服务于 Routa monorepo；路径规则对一般仓库同样成立，
    未识别的文件不产生 domain，由增量过滤层以 fail-open 兜底。
    """

    def release_trigger_config(self, project_root: Path) -> Path:
        return project_root / "docs" / "release-triggers.yaml"

    def should_ignore_changed_file(self, file_path: str) -> bool:
        return file_path.startswith(
            (
                "tmp/",
                "docs/",
                ".entrix/",
                ".code-review-graph/",
                "node_modules/",
            )
        )

    def domains_from_files(self, files: list[str]) -> set[str]:
        domains: set[str] = set()
        config_files = {
            "package.json",
            "package-lock.json",
            "Cargo.toml",
            "Cargo.lock",
            "api-contract.yaml",
            "eslint.config.mjs",
            "tsconfig.json",
            "pyproject.toml",
            "tools/entrix/file_budgets.json",
        }
        for file_path in files:
            suffix = Path(file_path).suffix.lower()
            name = Path(file_path).name
            lowered = file_path.lower()
            if suffix == ".rs" or lowered.startswith("crates/"):
                domains.add("rust")
            if suffix in {".ts", ".tsx", ".js", ".jsx", ".css", ".scss"} or lowered.startswith(
                ("src/", "apps/")
            ):
                domains.add("web")
            if suffix == ".py" or lowered.startswith("tools/entrix/"):
                domains.add("python")
            if file_path in config_files or name in config_files:
                domains.add("config")
        return domains

    def metric_domains(self, metric: Metric) -> set[str]:
        if metric.scope:
            return set(metric.scope)

        command = metric.command.lower()
        domains: set[str] = set()

        if "cargo " in command or "clippy" in command or "rust" in command:
            domains.add("rust")
        if any(
            token in command
            for token in (
                "npm ",
                "npx ",
                "eslint",
                "vitest",
                "playwright",
                "jscpd",
                "dependency-cruiser",
                "ast-grep",
                " semgrep",
                "semgrep ",
            )
        ):
            domains.add("web")
        if "python" in command or "pytest" in command or "entrix" in command:
            domains.add("python")
        if "audit" in command:
            domains.add("config")

        if not domains:
            domains.add("global")
        return domains


RoutaPreset = DefaultPreset
"""历史名称别名；新代码请使用 :class:`DefaultPreset`。"""
