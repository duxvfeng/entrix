"""Tests for the default single-file Harness template."""

import yaml
import pytest

from entrix.harness.template import (
    default_harness_config,
    render_default_harness,
    render_profile_harness,
)


def test_default_harness_template_limits_producer_parallelism():
    config = default_harness_config()

    assert config["settings"] == {
        "failure_mode": "closed",
        "max_parallel_producers": 1,
    }
    assert len(config["fitness"]["dimensions"]) == 5
    assert len(config["review_triggers"]["rules"]) == 5
    builtins = {producer["builtin"] for producer in config["evidence_producers"]}
    assert {"entrix-fitness", "entrix-review-trigger", "diff-stats"} <= builtins


def test_render_default_harness_is_valid_yaml_with_one_trailing_newline():
    rendered = render_default_harness()

    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")
    assert yaml.safe_load(rendered)["version"] == "harness/v1"


@pytest.mark.parametrize(
    ("profile", "expected_command", "expected_marker"),
    [
        ("python", "pytest", "pyproject.toml"),
        ("node-typescript", "npm run test --if-present", "package.json"),
        ("java-maven", "mvn -B -T1", "pom.xml"),
        ("java-gradle", "--max-workers=1", "build.gradle"),
        ("go", "go test ./...", "go.mod"),
        ("rust", "cargo test --workspace", "Cargo.toml"),
    ],
)
def test_profile_template_uses_language_commands(profile, expected_command, expected_marker):
    config = yaml.safe_load(render_profile_harness(profile))

    serialized = yaml.safe_dump(config, sort_keys=False)
    assert expected_command in serialized
    assert config["when"]["files_exist"] == [expected_marker]
    assert config["when"]["branch"]["exclude"] == ["docs/**"]


def test_java_templates_limit_internal_parallelism():
    maven = yaml.safe_load(render_profile_harness("java-maven"))
    gradle = yaml.safe_load(render_profile_harness("java-gradle"))

    maven_commands = [
        metric["command"]
        for dimension in maven["fitness"]["dimensions"]
        for metric in dimension["metrics"]
    ]
    gradle_commands = [
        metric["command"]
        for dimension in gradle["fitness"]["dimensions"]
        for metric in dimension["metrics"]
    ]
    assert any("-T1" in command and "forkCount=1" in command for command in maven_commands)
    assert all("--max-workers=1" in command for command in gradle_commands)


@pytest.mark.parametrize("profile", ["generic", "python", "node-typescript", "java-maven", "java-gradle", "go", "rust"])
def test_profile_template_is_valid_harness_yaml(profile):
    from entrix.harness.config import load_harness_config

    # The loader only needs a path; this test ensures every generated shape is accepted.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "harness.yaml"
        path.write_text(render_profile_harness(profile), encoding="utf-8")
        assert load_harness_config(path).version == "harness/v1"
