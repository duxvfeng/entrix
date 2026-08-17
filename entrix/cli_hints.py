"""Parser hints and output-safe next-step guidance for Entrix CLI."""
from __future__ import annotations

import argparse
import difflib
from typing import Any, TextIO

NEXT_STEPS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("init",): ("entrix harness validate harness.yaml", "entrix run"),
    ("harness", "validate"): ("entrix harness run --json",),
    ("run",): ("entrix harness run --json",),
    ("review-trigger",): ("entrix harness run --json",),
}


class HintingArgumentParser(argparse.ArgumentParser):
    """Argument parser that suggests registered subcommands on close typos."""

    def __init__(
        self, *args: Any, command_path: tuple[str, ...] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.command_path = command_path or ("entrix",)

    def _check_value(self, action: argparse.Action, value: object) -> None:
        try:
            super()._check_value(action, value)
        except argparse.ArgumentError as error:
            if isinstance(action, argparse._SubParsersAction) and isinstance(value, str):
                matches = difflib.get_close_matches(value, list(action.choices), n=1, cutoff=0.72)
                if matches:
                    suggestion = " ".join((*self.command_path, matches[0]))
                    error.message = f"{error.message}\n你是否想输入：{suggestion}"
            raise


def render_next_steps(command_path: tuple[str, ...]) -> tuple[str, ...]:
    """Return configured guidance for one successful command path."""
    return NEXT_STEPS.get(command_path, ())


def should_show_next_steps(args: argparse.Namespace, exit_code: int) -> bool:
    """Keep hints out of machine-readable and persistent command output."""
    command_path = tuple(getattr(args, "command_path", ()))
    return (
        exit_code == 0
        and not getattr(args, "json", False)
        and getattr(args, "output", None) != "-"
        and command_path not in {("stop-gate",), ("serve",)}
    )


def print_next_steps(command_path: tuple[str, ...], stream: TextIO) -> None:
    """Write configured next steps to stderr after successful human output."""
    steps = render_next_steps(command_path)
    if not steps:
        return
    print("下一步：", file=stream)
    for step in steps:
        print(f"  {step}", file=stream)
