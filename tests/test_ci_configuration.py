"""Regression checks for CI commands that exercise the current checkout."""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_python_baseline_is_311_for_package_and_release_ci() -> None:
    package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert package["project"]["requires-python"] == ">=3.11"
    assert package["tool"]["ruff"]["target-version"] == "py311"

    for workflow_name in ("ci.yml", "build.yml"):
        workflow = (ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        assert "3.10" not in workflow


def test_ci_runs_the_test_suite_on_windows() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    payload = yaml.safe_load(workflow)
    matrix = payload["jobs"]["test"]["strategy"]["matrix"]["include"]

    assert {"os": "windows-latest", "python-version": "3.12"} in matrix


def test_ci_has_a_dedicated_mcp_contract_job() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    payload = yaml.safe_load(workflow)
    steps = payload["jobs"]["mcp-contract"]["steps"]

    assert any('.[dev,mcp]' in step.get("run", "") for step in steps)
    assert any("tests/test_mcp_stdio.py" in step.get("run", "") for step in steps)


def test_ci_publishes_junit_and_coverage_reports() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "--junitxml=.artifacts/pytest.xml" in workflow
    assert "--cov=entrix" in workflow
    assert "scripts/write_test_summary.py" in workflow
    assert "Upload test reports" in workflow


def test_type_checking_uses_project_mypy_configuration() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    payload = yaml.safe_load(workflow)
    steps = payload["jobs"]["test"]["steps"]
    type_step = next(step for step in steps if step.get("name") == "Type checking")

    assert type_step["run"].splitlines() == ["mypy"]
    assert "continue-on-error" not in type_step


def test_defense_workflow_uses_the_checked_out_entrix_package() -> None:
    workflow = (ROOT / ".github" / "workflows" / "defense.yml").read_text(encoding="utf-8")

    assert 'python -m pip install -e ".[dev]"' in workflow
    assert "docs/fitness" not in workflow
    assert "uvx --from entrix entrix" not in workflow
    assert "python -m entrix harness validate harness.yaml" in workflow
    assert "python -m entrix run" in workflow
    assert "python -m entrix review-trigger" in workflow
    assert "--tier fast" in workflow
    assert "--scope ci" in workflow
    assert "--tier normal" not in workflow


def test_skill_regression_targets_harness_configuration() -> None:
    script = (ROOT / "scripts" / "skill_regression.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "skill-regression.yml").read_text(
        encoding="utf-8"
    )

    assert "docs/fitness" not in script
    assert "harness.yaml" in script
    assert "ENTRIX_CMD=(python3 -m entrix)" in script
    assert "docs/fitness" not in workflow
    assert "harness.yaml" in workflow


def test_release_workflow_builds_verified_five_platform_assets() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "build.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    payload = yaml.safe_load(workflow)
    matrix = payload["jobs"]["build"]["strategy"]["matrix"]["include"]
    runners = {entry["os"] for entry in matrix}

    assert {
        "windows-latest",
        "ubuntu-latest",
        "ubuntu-24.04-arm",
        "macos-15-intel",
        "macos-14",
    } <= runners
    assert 'pip install -e ".[mcp]"' in workflow
    assert "--onefile" in workflow
    assert "--collect-all fastmcp" in workflow
    assert "--collect-all tree_sitter_language_pack" in workflow
    assert ".sha256" in workflow
    assert "softprops/action-gh-release" in workflow

    python_job = workflow.split("build-python-package:", 1)[1]
    assert 'pip install -e ".[mcp]"' not in python_job


def test_release_upload_resolves_a_tag_for_every_trigger() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "build.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    payload = yaml.safe_load(workflow)
    release_steps = payload["jobs"]["release"]["steps"]
    upload_step = next(step for step in release_steps if step.get("uses") == "softprops/action-gh-release@v2")

    assert upload_step["with"]["tag_name"] == "${{ steps.release_tag.outputs.tag }}"
    assert upload_step["with"]["target_commitish"] == "${{ github.sha }}"
    assert upload_step["with"]["overwrite_files"] is True
    assert "Resolve release tag" in workflow
    assert payload["jobs"]["release"]["if"] == (
        "github.event_name == 'release' || github.event_name == 'workflow_dispatch' "
        "|| startsWith(github.ref, 'refs/tags/v')"
    )
    assert "fetch-depth: 0" in workflow
    assert "git describe --tags --abbrev=0 HEAD" in workflow
    assert "Manual release runs require an existing tag reachable from HEAD" in workflow
    assert not any(step.get("uses") == "actions/create-release@v1" for step in release_steps)


def test_release_workflow_rejects_tag_and_manifest_version_mismatch() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")

    assert "Validate release version" in workflow
    assert "release_tag != f\"v{version}\"" in workflow
    assert ".claude-plugin/plugin.json" in workflow
    assert ".claude-plugin/marketplace.json" in workflow
