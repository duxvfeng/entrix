"""Stop hook CLI 入口测试 —— 验证 Claude Code Stop hook 契约。"""

import io
import json
import sys
from pathlib import Path

from entrix.stop_gate.hook import (
    derive_changed_files,
    find_harness_config,
    has_fitness_specs,
    read_hook_payload,
    run_stop_gate_hook,
)


def _write_spec(repo: Path, command: str, hard_gate: bool = True) -> None:
    fitness_dir = repo / "docs" / "fitness"
    fitness_dir.mkdir(parents=True, exist_ok=True)
    (fitness_dir / "code-quality.md").write_text(
        f"""---
dimension: code_quality
weight: 100
threshold:
  pass: 100
  warn: 80
metrics:
  - name: smoke
    command: {json.dumps(command)}
    hard_gate: {str(hard_gate).lower()}
    tier: fast
---

# Code Quality
""",
        encoding="utf-8",
    )


def _run(payload: dict | str, cwd: Path, monkeypatch) -> tuple[int, str]:
    monkeypatch.chdir(cwd)
    stream = io.StringIO()
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    rc = run_stop_gate_hook(
        input_stream=io.StringIO(raw),
        output_stream=stream,
    )
    return rc, stream.getvalue()


class TestReadHookPayload:
    def test_valid_json(self):
        payload = read_hook_payload(io.StringIO('{"session_id": "s1"}'))
        assert payload == {"session_id": "s1"}

    def test_empty_stdin(self):
        assert read_hook_payload(io.StringIO("")) == {}

    def test_invalid_json(self):
        assert read_hook_payload(io.StringIO("not json")) == {}

    def test_non_dict_payload(self):
        assert read_hook_payload(io.StringIO('["list"]')) == {}


class TestFitnessSpecDetection:
    def test_detects_md_specs(self, tmp_path: Path):
        fitness = tmp_path / "docs" / "fitness"
        fitness.mkdir(parents=True)
        (fitness / "code-quality.md").write_text("---\n---\n")
        assert has_fitness_specs(tmp_path) is True

    def test_detects_manifest_only(self, tmp_path: Path):
        fitness = tmp_path / "docs" / "fitness"
        fitness.mkdir(parents=True)
        (fitness / "manifest.yaml").write_text("dimensions: []\n")
        assert has_fitness_specs(tmp_path) is True

    def test_empty_fitness_dir(self, tmp_path: Path):
        (tmp_path / "docs" / "fitness").mkdir(parents=True)
        assert has_fitness_specs(tmp_path) is False

    def test_missing_fitness_dir(self, tmp_path: Path):
        assert has_fitness_specs(tmp_path) is False


class TestHarnessConfigDiscovery:
    def test_prefers_root_harness_config(self, tmp_path: Path):
        root_config = tmp_path / "harness.yaml"
        nested_config = tmp_path / ".harness" / "harness.yaml"
        root_config.write_text("version: harness/v1\n")
        nested_config.parent.mkdir()
        nested_config.write_text("version: harness/v1\n")

        assert find_harness_config(tmp_path) == root_config

    def test_uses_nested_harness_config(self, tmp_path: Path):
        nested_config = tmp_path / ".harness" / "harness.yaml"
        nested_config.parent.mkdir()
        nested_config.write_text("version: harness/v1\n")

        assert find_harness_config(tmp_path) == nested_config


class TestDeriveChangedFiles:
    def test_non_git_directory_returns_empty(self, tmp_path: Path, monkeypatch):
        class Result:
            returncode = 1
            stdout = ""

        monkeypatch.setattr("entrix.stop_gate.hook.subprocess.run", lambda *args, **kwargs: Result())
        assert derive_changed_files(tmp_path) == []

    def test_parses_porcelain_entries(self, tmp_path: Path):
        import subprocess

        def git(*args: str) -> None:
            subprocess.run(
                ["git", *args], cwd=tmp_path, check=True, capture_output=True
            )

        git("init")
        git("config", "user.email", "test@test.com")
        git("config", "user.name", "Test")
        (tmp_path / "a.py").write_text("a = 1\n")
        git("add", "a.py")
        git("commit", "-m", "initial")
        (tmp_path / "a.py").write_text("a = 2\n")
        (tmp_path / "b.py").write_text("b = 1\n")

        changed = derive_changed_files(tmp_path)
        assert "a.py" in changed
        assert "b.py" in changed


class TestRunStopGateHook:
    def test_routes_root_harness_config_to_runner(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "harness.yaml"
        config_path.write_text("version: harness/v1\n")
        calls = {}

        class Runner:
            def __init__(self, path):
                calls["config_path"] = path

            def run(self, context):
                calls["context"] = context
                return type("Verdict", (), {"status": type("Status", (), {"value": "pass"})(), "summary": ""})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)

        rc, out = _run({"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch)

        assert rc == 0
        assert out == ""
        assert calls["config_path"] == config_path
        assert calls["context"]["workspace"] == tmp_path

    def test_passes_branch_and_base_ref_to_harness_runner(self, tmp_path: Path, monkeypatch):
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n")
        calls = {}

        class Runner:
            def __init__(self, path):
                pass

            def run(self, context):
                calls["context"] = context
                return type("Verdict", (), {"status": "pass", "summary": ""})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)

        output = io.StringIO()
        rc = run_stop_gate_hook(
            base_ref="origin/main",
            input_stream=io.StringIO(
                json.dumps({"session_id": "s1", "cwd": str(tmp_path), "branch": "feature/check"})
            ),
            output_stream=output,
        )

        assert rc == 0
        assert calls["context"]["branch"] == "feature/check"
        assert calls["context"]["base_ref"] == "origin/main"

    def test_preserves_none_base_ref_for_legacy_stop_gate(self, tmp_path: Path, monkeypatch):
        _write_spec(tmp_path, f'{sys.executable} -c "print(\'ok\')"')
        calls = {}

        class Adapter:
            def __init__(self, **_kwargs):
                pass

            def on_before_stop(self, context):
                calls["context"] = context
                return type("Decision", (), {"allow_stop": True, "feedback": ""})()

        monkeypatch.setattr("entrix.stop_gate.adapter.StopGateAdapter", Adapter)

        rc, output = _run({"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch)

        assert rc == 0
        assert output == ""
        assert calls["context"]["base_ref"] is None

    def test_routes_nested_harness_config_to_runner(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / ".harness" / "harness.yaml"
        config_path.parent.mkdir()
        config_path.write_text("version: harness/v1\n")

        class Runner:
            def __init__(self, path):
                assert path == config_path

            def run(self, context):
                return type("Verdict", (), {"status": type("Status", (), {"value": "pass"})(), "summary": ""})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)

        rc, out = _run({"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch)

        assert rc == 0
        assert out == ""

    def test_harness_error_blocks_stop(self, tmp_path: Path, monkeypatch):
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n")

        class Runner:
            def __init__(self, path):
                pass

            def run(self, context):
                raise ValueError("invalid harness")

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)

        rc, out = _run({"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch)

        assert rc == 0
        assert json.loads(out)["decision"] == "block"

    def test_allow_when_no_fitness_specs(self, tmp_path: Path, monkeypatch):
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}
        rc, out = _run(payload, tmp_path, monkeypatch)
        assert rc == 0
        assert out == ""

    def test_allow_when_stop_hook_active(self, tmp_path: Path, monkeypatch):
        """stop_hook_active 为真时必须放行，且不应触发门禁。"""
        _write_spec(tmp_path, f'{sys.executable} -c "raise SystemExit(1)"')
        payload = {
            "session_id": "s1",
            "cwd": str(tmp_path),
            "hook_event_name": "Stop",
            "stop_hook_active": True,
        }
        rc, out = _run(payload, tmp_path, monkeypatch)
        assert rc == 0
        assert out == ""
        # 门禁未运行 → 没有状态文件
        assert not (tmp_path / ".claude" / "stop-gate" / "state.json").exists()

    def test_env_var_disables_gate(self, tmp_path: Path, monkeypatch):
        _write_spec(tmp_path, f'{sys.executable} -c "raise SystemExit(1)"')
        monkeypatch.setenv("ENTRIX_STOP_GATE_DISABLED", "1")
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}
        rc, out = _run(payload, tmp_path, monkeypatch)
        assert rc == 0
        assert out == ""

    def test_block_on_hard_gate_failure(self, tmp_path: Path, monkeypatch):
        _write_spec(tmp_path, f'{sys.executable} -c "raise SystemExit(1)"')
        payload = {
            "session_id": "s1",
            "cwd": str(tmp_path),
            "hook_event_name": "Stop",
            "reason": "end_turn",
        }
        rc, out = _run(payload, tmp_path, monkeypatch)
        assert rc == 0
        decision = json.loads(out)
        assert decision["decision"] == "block"
        assert decision["reason"]
        # 状态落盘，便于事后审计
        assert (tmp_path / ".claude" / "stop-gate" / "state.json").exists()

    def test_allow_when_gate_passes(self, tmp_path: Path, monkeypatch):
        _write_spec(tmp_path, f'{sys.executable} -c "print(\'ok\')"', hard_gate=False)
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}
        rc, out = _run(payload, tmp_path, monkeypatch)
        assert rc == 0
        assert out == ""

    def test_invalid_stdin_falls_back_to_cwd(self, tmp_path: Path, monkeypatch):
        """损坏的 stdin 按空载荷处理，未配置仓库直接放行。"""
        rc, out = _run("not-json", tmp_path, monkeypatch)
        assert rc == 0
        assert out == ""

    def test_missing_cwd_uses_process_cwd(self, tmp_path: Path, monkeypatch):
        payload = {"session_id": "s1", "hook_event_name": "Stop"}
        rc, out = _run(payload, tmp_path, monkeypatch)
        assert rc == 0
        assert out == ""
