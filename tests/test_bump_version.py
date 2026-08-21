"""Tests for bumping the release version across pinned locations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bump_version import bump_version


def _write_release_fixtures(root: Path, version: str) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "entrix"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    plugin_dir = root / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "version": version,
                "mcpServers": {"entrix": {"env": {"ENTRIX_BINARY_VERSION": version}}},
                "hooks": {"Stop": [{"hooks": [{"env": {"ENTRIX_BINARY_VERSION": version}}]}]},
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "version": version,
                        "release": {"asset_prefix": f"entrix-{version}-"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_plugin_binary_contract.py").write_text(
        f'    assert package_version == "{version}"\n',
        encoding="utf-8",
    )


def test_bump_version_rewrites_all_pinned_locations(tmp_path: Path) -> None:
    _write_release_fixtures(tmp_path, "0.1.0")

    changed = bump_version(tmp_path, "0.2.0")

    assert [(path.name, count) for path, count in changed] == [
        ("pyproject.toml", 1),
        ("plugin.json", 3),
        ("marketplace.json", 2),
        ("test_plugin_binary_contract.py", 1),
    ]
    assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    plugin = json.loads(
        (tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert plugin["version"] == "0.2.0"
    assert plugin["mcpServers"]["entrix"]["env"]["ENTRIX_BINARY_VERSION"] == "0.2.0"
    marketplace = json.loads(
        (tmp_path / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert marketplace["plugins"][0]["release"]["asset_prefix"] == "entrix-0.2.0-"


def test_bump_version_aborts_before_writing_on_count_mismatch(tmp_path: Path) -> None:
    _write_release_fixtures(tmp_path, "0.1.0")
    plugin_path = tmp_path / ".claude-plugin" / "plugin.json"
    plugin_path.write_text(
        plugin_path.read_text(encoding="utf-8").replace(
            '"ENTRIX_BINARY_VERSION": "0.1.0"', '"ENTRIX_BINARY_VERSION": "pinned"', 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected 3"):
        bump_version(tmp_path, "0.2.0")

    assert 'version = "0.1.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")


def test_bump_version_rejects_invalid_version(tmp_path: Path) -> None:
    _write_release_fixtures(tmp_path, "0.1.0")

    with pytest.raises(ValueError, match="X.Y.Z"):
        bump_version(tmp_path, "0.2")

    with pytest.raises(ValueError, match="already 0.1.0"):
        bump_version(tmp_path, "0.1.0")
