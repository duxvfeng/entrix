from pathlib import Path

import pytest

from entrix.harness.profiles import (
    ProfileDetectionError,
    detect_profile,
    matching_profiles,
    resolve_profile,
)


def test_detects_python_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    assert matching_profiles(tmp_path) == ("python",)
    assert detect_profile(tmp_path) == "python"
    assert resolve_profile("auto", tmp_path) == "python"


@pytest.mark.parametrize(
    ("marker", "profile"),
    [
        ("package.json", "node-typescript"),
        ("pom.xml", "java-maven"),
        ("build.gradle.kts", "java-gradle"),
        ("go.mod", "go"),
        ("Cargo.toml", "rust"),
    ],
)
def test_detects_supported_profile_markers(tmp_path: Path, marker: str, profile: str) -> None:
    (tmp_path / marker).write_text("", encoding="utf-8")

    assert detect_profile(tmp_path) == profile


def test_unknown_repository_falls_back_to_generic(tmp_path: Path) -> None:
    assert matching_profiles(tmp_path) == ()
    assert detect_profile(tmp_path) == "generic"
    assert resolve_profile("auto", tmp_path) == "generic"


def test_multiple_profiles_require_explicit_selection(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ProfileDetectionError, match="--profile"):
        detect_profile(tmp_path)
    assert resolve_profile("java-maven", tmp_path) == "java-maven"


def test_invalid_profile_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="profile"):
        resolve_profile("kotlin", tmp_path)
