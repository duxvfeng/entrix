"""Entrix fitness 与 review-trigger 包。"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from entrix.stop_gate import HarnessRunner, run_stop_gate_hook


def _package_version() -> str:
    """Read the installed distribution version, with a source-tree fallback."""
    try:
        return version("entrix")
    except PackageNotFoundError:
        try:
            import tomllib

            project = tomllib.loads(
                (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
                    encoding="utf-8"
                )
            )
            return str(project["project"]["version"])
        except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
            return "unknown"


__version__ = _package_version()

__all__ = [
    "HarnessRunner",
    "run_stop_gate_hook",
    "__version__",
]
