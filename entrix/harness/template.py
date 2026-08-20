"""Default single-file Harness configuration for ``entrix init``."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from entrix.harness.lint_config import (
    generate_metrics_from_lint_config,
    get_dimension_weights,
    should_use_configured_lints,
)
from entrix.harness.profiles import marker_for_profile


def default_harness_config() -> dict[str, Any]:
    """Return the default Harness configuration as structured data."""
    return {
        "version": "harness/v1",
        "settings": {"failure_mode": "closed", "max_parallel_producers": 1},
        "fitness": {
            "dimensions": [
                {
                    "dimension": "code_quality",
                    "weight": 35,
                    "threshold": {"pass": 100, "warn": 90},
                    "metrics": [
                        {
                            "name": "ruff_pass",
                            "command": "ruff check . 2>&1",
                            "hard_gate": True,
                            "tier": "fast",
                            "description": "Ruff must pass with no lint errors.",
                        },
                        {
                            "name": "no_new_debug_prints",
                            "command": (
                                'base_ref="${ENTRIX_FITNESS_BASE:-HEAD}"\n'
                                "git diff --unified=0 \"$base_ref\" -- . ':(exclude)docs/**' 2>/dev/null | "
                                "grep -E '^\\+[^+].*\\b(print|pprint)\\(' | grep -vE '(^\\+\\+\\+|tests?/|test_)' | "
                                "wc -l | awk '{print \"new_debug_prints:\", $1}'"
                            ),
                            "pattern": "new_debug_prints: 0",
                            "tier": "fast",
                            "description": "Production code should not grow accidental debug prints.",
                        },
                    ],
                },
                {
                    "dimension": "testability",
                    "weight": 40,
                    "threshold": {"pass": 100, "warn": 90},
                    "metrics": [
                        {
                            "name": "pytest_pass",
                            "command": "pytest 2>&1",
                            "hard_gate": True,
                            "tier": "normal",
                            "description": "The repository test suite must pass.",
                        }
                    ],
                },
                {
                    "dimension": "release_readiness",
                    "weight": 25,
                    "threshold": {"pass": 100, "warn": 90},
                    "metrics": [
                        {
                            "name": "cli_help_smoke",
                            "command": "python3 -m entrix --help 2>&1",
                            "pattern": "usage: entrix",
                            "hard_gate": True,
                            "tier": "fast",
                            "description": "The local package entrypoint must still render CLI help.",
                        },
                        {
                            "name": "package_build_pass",
                            "command": "python3 -m build --no-isolation 2>&1",
                            "hard_gate": True,
                            "tier": "normal",
                            "description": "The project must still produce source and wheel distributions.",
                        },
                    ],
                },
                {
                    "dimension": "observability",
                    "weight": 0,
                    "threshold": {"pass": 100, "warn": 80},
                    "metrics": [
                        {
                            "name": "tracing_signal_available",
                            "command": "./scripts/obs/check-tracing-signal.sh 2>&1",
                            "pattern": "signal_ok",
                            "tier": "deep",
                            "execution_scope": "staging",
                            "gate": "advisory",
                            "kind": "holistic",
                            "analysis": "dynamic",
                            "stability": "noisy",
                            "evidence_type": "probe",
                            "scope": ["web", "runtime"],
                            "run_when_changed": ["src/instrumentation.ts", "scripts/obs/**"],
                            "owner": "platform",
                            "confidence": "high",
                            "description": "Verify tracing and runtime visibility signals in staging.",
                        },
                        {
                            "name": "tracing_signal_contract_declared",
                            "command": "printf 'signal_contract: pending\\n'",
                            "pattern": "signal_contract: pending",
                            "tier": "normal",
                            "execution_scope": "ci",
                            "gate": "soft",
                            "evidence_type": "manual_attestation",
                            "scope": ["docs", "runtime"],
                            "run_when_changed": ["harness.yaml", "src/instrumentation.ts"],
                            "owner": "platform",
                            "confidence": "medium",
                            "description": "Keep a lightweight CI-visible tracing contract.",
                        },
                    ],
                },
                {
                    "dimension": "performance",
                    "weight": 0,
                    "threshold": {"pass": 100, "warn": 80},
                    "metrics": [
                        {
                            "name": "latency_budget_probe_defined",
                            "command": "printf 'latency_budget: pending\\n'",
                            "pattern": "latency_budget: pending",
                            "tier": "normal",
                            "execution_scope": "ci",
                            "gate": "advisory",
                            "kind": "holistic",
                            "analysis": "dynamic",
                            "stability": "noisy",
                            "evidence_type": "probe",
                            "scope": ["web", "api", "runtime"],
                            "run_when_changed": ["harness.yaml", "src/**", "crates/**"],
                            "owner": "platform",
                            "confidence": "low",
                            "description": "Reserve a CI-visible latency budget evidence slot.",
                        },
                        {
                            "name": "runtime_budget_signal_unavailable",
                            "command": "graph:runtime-budget",
                            "tier": "deep",
                            "execution_scope": "prod_observation",
                            "gate": "advisory",
                            "kind": "holistic",
                            "analysis": "dynamic",
                            "stability": "noisy",
                            "evidence_type": "probe",
                            "scope": ["runtime", "performance"],
                            "run_when_changed": ["harness.yaml", "src/**", "crates/**"],
                            "owner": "platform",
                            "confidence": "unknown",
                            "description": "Placeholder for a future production runtime budget probe.",
                        },
                    ],
                },
            ]
        },
        "review_triggers": {
            "rules": [
                {
                    "name": "core_engine_change",
                    "type": "changed_paths",
                    "paths": [
                        "entrix/cli.py",
                        "entrix/engine.py",
                        "entrix/governance.py",
                        "entrix/review_trigger.py",
                        "entrix/presets/**",
                    ],
                    "severity": "high",
                    "action": "require_human_review",
                },
                {
                    "name": "packaging_or_workflow_change",
                    "type": "changed_paths",
                    "paths": ["pyproject.toml", ".github/workflows/**", "harness.yaml"],
                    "severity": "medium",
                    "action": "require_human_review",
                },
                {
                    "name": "sensitive_release_files",
                    "type": "sensitive_file_change",
                    "paths": ["pyproject.toml", "entrix/model.py", "entrix/review_trigger.py"],
                    "severity": "high",
                    "action": "require_human_review",
                },
                {
                    "name": "cross_boundary_engine_test_docs_change",
                    "type": "cross_boundary_change",
                    "boundaries": {
                        "engine": ["entrix/**"],
                        "tests": ["tests/**"],
                        "docs": ["docs/**"],
                    },
                    "min_boundaries": 2,
                    "severity": "medium",
                    "action": "require_human_review",
                },
                {
                    "name": "oversized_change",
                    "type": "diff_size",
                    "max_files": 10,
                    "max_added_lines": 400,
                    "max_deleted_lines": 250,
                    "severity": "medium",
                    "action": "require_human_review",
                },
            ]
        },
        "evidence_producers": [
            {
                "id": "fitness",
                "type": "fitness",
                "name": "Entrix Fitness",
                "builtin": "entrix-fitness",
            },
            {
                "id": "review-trigger",
                "type": "review-trigger",
                "name": "Review Trigger",
                "builtin": "entrix-review-trigger",
            },
            {
                "id": "diff-stats",
                "type": "diff",
                "name": "Git Diff Statistics",
                "builtin": "diff-stats",
            },
        ],
        "gate_policies": [
            {
                "name": "Fitness must pass",
                "severity": "hard",
                "rule": {"evidence_id": "fitness", "condition": 'status == "pass"'},
            },
            {
                "name": "Review trigger blocks stop",
                "severity": "blocked",
                "rule": {"evidence_id": "review-trigger", "condition": 'status == "fail"'},
            },
        ],
    }


def _language_dimensions(profile: str, repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Return the three weighted dimensions for a language profile."""
    # 检查是否使用配置的 lint 工具
    use_configured_lints = should_use_configured_lints(repo_root)

    if use_configured_lints:
        # 使用配置的 lint 工具
        configured_dimensions = generate_metrics_from_lint_config(profile, repo_root)

        if configured_dimensions:
            # 有配置的 lint 工具，使用配置
            return configured_dimensions
        else:
            # 没有配置的 lint 工具，使用默认的
            return _default_dimensions_for_profile(profile)
    else:
        # 使用传统硬编码的维度
        return _default_dimensions_for_profile(profile)


def _default_dimensions_for_profile(profile: str) -> list[dict[str, Any]]:
    """返回默认的硬编码维度配置（向后兼容）"""
    commands: dict[str, tuple[tuple[str, str, str], ...]] = {
        "python": (
            ("ruff_pass", "ruff check . 2>&1", "Ruff must pass with no lint errors."),
            ("pytest_pass", "python -m pytest 2>&1", "The Python test suite must pass."),
            ("package_build_pass", "python -m build --no-isolation 2>&1", "The Python package must build."),
        ),
        "node-typescript": (
            ("lint_pass", "npm run lint --if-present 2>&1", "The Node lint script must pass when present."),
            ("test_pass", "npm run test --if-present 2>&1", "The Node test script must pass when present."),
            ("build_pass", "npm run build --if-present 2>&1", "The Node build script must pass when present."),
        ),
        "java-maven": (
            ("maven_validate", "mvn -B -T1 -DskipTests validate 2>&1", "Maven validation must pass with one reactor thread."),
            (
                "maven_tests",
                "mvn -B -T1 -DforkCount=1 -DreuseForks=true test 2>&1",
                "Maven tests must pass with one reactor thread and one test JVM.",
            ),
            ("maven_package", "mvn -B -T1 -DskipTests package 2>&1", "Maven packaging must pass with one reactor thread."),
        ),
        "java-gradle": (
            (
                "gradle_check",
                "gradlew --no-daemon --max-workers=1 check -x test 2>&1",
                "Gradle checks must pass with one worker.",
            ),
            (
                "gradle_tests",
                "gradlew --no-daemon --max-workers=1 test 2>&1",
                "Gradle tests must pass with one worker.",
            ),
            (
                "gradle_build",
                "gradlew --no-daemon --max-workers=1 assemble 2>&1",
                "Gradle packaging must pass with one worker.",
            ),
        ),
        "go": (
            ("go_vet", "go vet ./... 2>&1", "Go vet must pass."),
            ("go_test", "go test ./... 2>&1", "Go tests must pass."),
            ("go_build", "go build ./... 2>&1", "Go packages must build."),
        ),
        "rust": (
            ("cargo_fmt", "cargo fmt --all -- --check 2>&1", "Rust formatting must be clean."),
            ("cargo_test", "cargo test --workspace 2>&1", "Rust workspace tests must pass."),
            ("cargo_build", "cargo build --workspace 2>&1", "Rust workspace must build."),
        ),
    }
    selected = commands[profile]
    dimensions: list[dict[str, Any]] = []
    for index, (name, command, description) in enumerate(selected):
        dimension_name = ("code_quality", "testability", "release_readiness")[index]
        metric: dict[str, Any] = {
            "name": name,
            "command": command,
            "hard_gate": True,
            "tier": "fast" if index == 0 else "normal",
            "description": description,
        }
        dimensions.append(
            {
                "dimension": dimension_name,
                "weight": (35, 40, 25)[index],
                "threshold": {"pass": 100, "warn": 90},
                "metrics": [metric],
            }
        )
    return dimensions


def _profile_review_rules(profile: str) -> list[dict[str, Any]]:
    """Return repository-neutral review triggers for a language profile."""
    manifest = {
        "python": "pyproject.toml",
        "node-typescript": "package.json",
        "java-maven": "pom.xml",
        "java-gradle": "build.gradle",
        "go": "go.mod",
        "rust": "Cargo.toml",
    }[profile]
    return [
        {
            "name": "source_change",
            "type": "changed_paths",
            "paths": ["src/**", "app/**", "lib/**", "cmd/**", "internal/**", "crates/**"],
            "severity": "high",
            "action": "require_human_review",
        },
        {
            "name": "build_configuration_change",
            "type": "changed_paths",
            "paths": [manifest, "harness.yaml", ".github/workflows/**"],
            "severity": "medium",
            "action": "require_human_review",
        },
        {
            "name": "oversized_change",
            "type": "diff_size",
            "max_files": 20,
            "max_added_lines": 600,
            "max_deleted_lines": 400,
            "severity": "medium",
            "action": "require_human_review",
        },
    ]


def profile_harness_config(profile: str, repo_root: Path | None = None) -> dict[str, Any]:
    """Return a language-specific Harness configuration."""
    if profile == "generic":
        return default_harness_config()
    if profile == "auto":
        raise ValueError("profile_harness_config() 需要已解析的 profile，不支持 auto")

    marker = marker_for_profile(profile, repo_root)
    if marker is None:
        raise ValueError(f"未知 profile：{profile}")

    config = deepcopy(default_harness_config())
    config["fitness"]["dimensions"] = _language_dimensions(profile, repo_root)
    config["review_triggers"]["rules"] = _profile_review_rules(profile)
    config["when"] = {
        "files_exist": [marker],
        "branch": {"exclude": ["docs/**"]},
    }
    for policy in config["gate_policies"]:
        policy["when"] = {"branch": {"exclude": ["docs/**"]}}
    return config


def render_profile_harness(profile: str, repo_root: Path | None = None) -> str:
    """Serialize a resolved profile configuration with one trailing newline."""
    return yaml.safe_dump(
        profile_harness_config(profile, repo_root), sort_keys=False, allow_unicode=True
    ).rstrip() + "\n"


def render_default_harness(profile: str = "generic", repo_root: Path | None = None) -> str:
    """Serialize the default configuration with a stable trailing newline."""
    return render_profile_harness(profile, repo_root)
