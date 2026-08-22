"""Repository-wide pytest configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def pytest_configure(config) -> None:
    """Use a writable, process-local temp root for concurrent Windows runs."""
    if getattr(config.option, "basetemp", None) is None:
        temp_parent = REPO_ROOT / ".pytest-runs"
        temp_parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(temp_parent / f"tmp-{os.getpid()}")


@pytest.fixture(autouse=True)
def isolate_entrix_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep user-scoped Stop Gate state inside each test workspace."""
    monkeypatch.setenv("ENTRIX_STATE_DIR", str(tmp_path / "entrix-state"))
