"""Project-language profiles used by ``entrix init``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ProfileDetectionError(ValueError):
    """Raised when automatic detection finds more than one project profile."""


@dataclass(frozen=True)
class ProfileDefinition:
    """A named profile and the repository markers that activate it."""

    name: str
    markers: tuple[str, ...]


PROFILE_DEFINITIONS: tuple[ProfileDefinition, ...] = (
    ProfileDefinition(
        "python",
        ("pyproject.toml", "pytest.ini", "requirements.txt", "setup.py", "setup.cfg"),
    ),
    ProfileDefinition("node-typescript", ("package.json", "tsconfig.json")),
    ProfileDefinition("java-maven", ("pom.xml",)),
    ProfileDefinition("java-gradle", ("build.gradle", "build.gradle.kts", "gradlew", "gradlew.bat")),
    ProfileDefinition("go", ("go.mod",)),
    ProfileDefinition("rust", ("Cargo.toml",)),
)

PROFILE_NAMES: tuple[str, ...] = ("auto", "generic") + tuple(
    definition.name for definition in PROFILE_DEFINITIONS
)

_DEFINITIONS_BY_NAME = {definition.name: definition for definition in PROFILE_DEFINITIONS}


def matching_profiles(repo_root: Path) -> tuple[str, ...]:
    """Return profiles whose marker files exist in ``repo_root``."""
    root = repo_root.resolve()
    matches: list[str] = []
    for definition in PROFILE_DEFINITIONS:
        if any((root / marker).exists() for marker in definition.markers):
            matches.append(definition.name)
    return tuple(matches)


def detect_profile(repo_root: Path) -> str:
    """Detect one profile, falling back to ``generic`` for unknown repositories."""
    matches = matching_profiles(repo_root)
    if not matches:
        return "generic"
    if len(matches) > 1:
        choices = ", ".join(matches)
        raise ProfileDetectionError(
            f"自动识别到多个项目 profile：{choices}。请使用 --profile <name> 明确选择。"
        )
    return matches[0]


def resolve_profile(profile: str, repo_root: Path) -> str:
    """Resolve an explicit or automatic profile name."""
    if profile not in PROFILE_NAMES:
        supported = ", ".join(PROFILE_NAMES)
        raise ValueError(f"未知 profile：{profile}。支持的 profile：{supported}")
    if profile == "auto":
        return detect_profile(repo_root)
    return profile


def marker_for_profile(profile: str, repo_root: Path | None = None) -> str | None:
    """Return an existing marker for a profile, or its canonical marker."""
    definition = _DEFINITIONS_BY_NAME.get(profile)
    if definition is None:
        return None
    if repo_root is not None:
        root = repo_root.resolve()
        for marker in definition.markers:
            if (root / marker).exists():
                return marker
    return definition.markers[0]
