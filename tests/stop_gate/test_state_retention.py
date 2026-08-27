"""StopGateStateStore session retention tests."""

import os
import time
from pathlib import Path

from entrix.stop_gate.revalidation import (
    MAX_SESSIONS_PER_WORKSPACE,
    RETENTION_DAYS,
    CachedVerdict,
    StopGateStateStore,
)


def _save_verdict(store: StopGateStateStore, workspace: Path, name: str) -> None:
    store.save(workspace, name, CachedVerdict(fingerprint="fp", status="fail", summary=name))


def _marker(session_id: str) -> str:
    import hashlib

    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def test_save_prunes_expired_sessions(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = StopGateStateStore(tmp_path / "state")

    for name in ("old-1", "old-2", "fresh"):
        _save_verdict(store, workspace, name)

    sessions_dir = store.sessions_dir(workspace)
    stale_time = time.time() - (RETENTION_DAYS + 1) * 86400
    os.utime(sessions_dir / f"{_marker('old-1')}.json", (stale_time, stale_time))
    os.utime(sessions_dir / f"{_marker('old-2')}.json", (stale_time, stale_time))

    _save_verdict(store, workspace, "trigger")

    names = {path.stem for path in sessions_dir.glob("*.json")}
    assert _marker("old-1") not in names
    assert _marker("old-2") not in names
    assert _marker("fresh") in names
    assert _marker("trigger") in names


def test_save_enforces_count_cap(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = StopGateStateStore(tmp_path / "state")

    for index in range(MAX_SESSIONS_PER_WORKSPACE + 5):
        _save_verdict(store, workspace, f"session-{index}")

    sessions = list(store.sessions_dir(workspace).glob("*.json"))
    assert len(sessions) == MAX_SESSIONS_PER_WORKSPACE


def test_prune_tolerates_oserror_on_single_file(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = StopGateStateStore(tmp_path / "state")
    _save_verdict(store, workspace, "existing")

    original_unlink = Path.unlink

    def flaky_unlink(self, missing_ok=False):
        if self.suffix == ".json":
            raise OSError("permission denied")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    # 不应抛出异常：单文件删除失败被忽略
    _save_verdict(store, workspace, "new-session")


def test_trust_files_are_not_pruned(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    config = workspace / "harness.yaml"
    config.write_text("version: harness/v1\n", encoding="utf-8")
    store = StopGateStateStore(tmp_path / "state")

    store.trust_config(workspace, config)

    for index in range(3):
        _save_verdict(store, workspace, f"session-{index}")

    trust_dir = tmp_path / "state" / "trust"
    assert trust_dir.is_dir()
    assert len(list(trust_dir.glob("*.json"))) == 1
