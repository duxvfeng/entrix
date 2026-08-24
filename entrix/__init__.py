"""Entrix fitness 与 review-trigger 包。"""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from entrix.stop_gate import HarnessRunner, run_stop_gate_hook


def _package_version() -> str:
    """Read the source-tree version, falling back to installed metadata."""
    try:
        project = tomllib.loads(
            (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )
        return str(project["project"]["version"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        try:
            return version("entrix")
        except PackageNotFoundError:
            return "unknown"


__version__ = _package_version()

__all__ = [
    "HarnessRunner",
    "run_stop_gate_hook",
    "__version__",
]
