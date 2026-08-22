"""Tests for short-lived Stop Gate phase state."""

import json
from pathlib import Path

import pytest

from entrix.stop_gate.phase import clear_phase, consume_phase, read_phase, write_phase


def test_write_phase_persists_mode_for_workspace(tmp_path: Path) -> None:
    write_phase(tmp_path, "planning")

    assert read_phase(tmp_path) == "planning"
    assert (tmp_path / ".harness" / "runtime" / "phase.json").is_file()


def test_read_phase_cleans_expired_state(tmp_path: Path) -> None:
    write_phase(tmp_path, "implementation", ttl_seconds=0)

    assert read_phase(tmp_path) is None
    assert not (tmp_path / ".harness" / "runtime" / "phase.json").exists()


def test_read_phase_rejects_state_for_another_workspace(tmp_path: Path) -> None:
    write_phase(tmp_path, "planning")
    phase_path = tmp_path / ".harness" / "runtime" / "phase.json"
    payload = json.loads(phase_path.read_text(encoding="utf-8"))
    payload["workspace"] = str(tmp_path.parent / "other-workspace")
    phase_path.write_text(json.dumps(payload), encoding="utf-8")

    assert read_phase(tmp_path) is None
    assert not phase_path.exists()


def test_write_phase_replaces_target_with_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replaced: dict[str, Path] = {}
    original_replace = Path.replace

    def record_replace(source: Path, target: Path) -> Path:
        replaced["source"] = source
        replaced["target"] = target
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", record_replace)
    write_phase(tmp_path, "planning")

    assert replaced["source"].suffix == ".tmp"
    assert replaced["target"] == tmp_path / ".harness" / "runtime" / "phase.json"
    assert not replaced["source"].exists()


def test_consume_phase_only_consumes_matching_one_shot_state(tmp_path: Path) -> None:
    write_phase(tmp_path, "init", one_shot=True)

    assert consume_phase(tmp_path, "planning") is False
    assert consume_phase(tmp_path, "init") is True
    assert consume_phase(tmp_path, "init") is False


def test_session_phase_states_do_not_overwrite_each_other(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setenv("ENTRIX_STATE_DIR", str(state_dir))

    write_phase(tmp_path, "planning", session_id="session-a")
    write_phase(tmp_path, "implementation", session_id="session-b")

    assert read_phase(tmp_path, session_id="session-a") == "planning"
    assert read_phase(tmp_path, session_id="session-b") == "implementation"
    assert not (tmp_path / ".harness" / "runtime" / "phase.json").exists()


def test_clear_phase_removes_session_and_legacy_markers(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setenv("ENTRIX_STATE_DIR", str(state_dir))

    write_phase(tmp_path, "planning")
    write_phase(tmp_path, "implementation", session_id="session-a")

    assert clear_phase(tmp_path, session_id="session-a") == 2
    assert read_phase(tmp_path) is None
    assert read_phase(tmp_path, session_id="session-a") is None


@pytest.mark.parametrize("mode", ["", "brainstorm", "stop-gate"])
def test_write_phase_rejects_unknown_modes(tmp_path: Path, mode: str) -> None:
    with pytest.raises(ValueError, match="phase mode"):
        write_phase(tmp_path, mode)
