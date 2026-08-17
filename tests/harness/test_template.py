"""Tests for the default single-file Harness template."""

import yaml

from entrix.harness.template import default_harness_config, render_default_harness


def test_default_harness_template_contains_inline_quality_configuration():
    config = default_harness_config()

    assert len(config["fitness"]["dimensions"]) == 5
    assert len(config["review_triggers"]["rules"]) == 5
    builtins = {producer["builtin"] for producer in config["evidence_producers"]}
    assert {"entrix-fitness", "entrix-review-trigger", "diff-stats"} <= builtins


def test_render_default_harness_is_valid_yaml_with_one_trailing_newline():
    rendered = render_default_harness()

    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")
    assert yaml.safe_load(rendered)["version"] == "harness/v1"
