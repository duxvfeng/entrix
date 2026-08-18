"""Stop hook CLI 入口测试 —— 验证 Claude Code Stop hook 契约。"""

import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from entrix.stop_gate.hook import (
    derive_changed_files,
    find_harness_config,
    read_hook_payload,
    run_stop_gate_hook,
    main as stop_gate_main,
    workspace_fingerprint,
)


def _run(
    payload: dict | str,
    cwd: Path,
    monkeypatch,
    *,
    state_dir: Path | None = None,
) -> tuple[int, str]:
    monkeypatch.chdir(cwd)
    stream = io.StringIO()
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    kwargs = {
        "input_stream": io.StringIO(raw),
        "output_stream": stream,
    }
    if state_dir is not None:
        kwargs["state_dir"] = state_dir
    rc = run_stop_gate_hook(**kwargs)
    return rc, stream.getvalue()


def test_workspace_fingerprint_changes_when_file_content_changes(tmp_path: Path):
    """A same-status edit must invalidate the cached Stop Gate verdict."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "entrix@example.invalid"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Entrix Tests"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    source = tmp_path / "source.txt"
    source.write_text("before", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    before = workspace_fingerprint(tmp_path)
    source.write_text("after", encoding="utf-8")
    after = workspace_fingerprint(tmp_path)

    assert before is not None
    assert after is not None
    assert before != after


def test_workspace_fingerprint_changes_in_ignored_nested_workspace(tmp_path: Path):
    """A workspace nested under an unrelated Git root uses its own files."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "entrix@example.invalid"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Entrix Tests"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / ".gitignore").write_text("nested-workspace/\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    workspace = tmp_path / "nested-workspace"
    workspace.mkdir()
    source = workspace / "source.txt"
    source.write_text("before", encoding="utf-8")

    before = workspace_fingerprint(workspace)
    source.write_text("after-and-longer", encoding="utf-8")
    after = workspace_fingerprint(workspace)

    assert before is not None
    assert after is not None
    assert before != after


def test_workspace_fingerprint_includes_nested_harness_config(tmp_path: Path):
    """An active nested Harness config must invalidate non-Git cached evidence."""
    config_path = tmp_path / ".harness" / "harness.yaml"
    config_path.parent.mkdir()
    config_path.write_text("version: harness/v1\n", encoding="utf-8")

    before = workspace_fingerprint(tmp_path)
    config_path.write_text("version: harness/v1\nwhen: {}\n", encoding="utf-8")
    after = workspace_fingerprint(tmp_path)

    assert before is not None
    assert after is not None
    assert before != after


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
    def test_ignores_legacy_fitness_files_without_harness(self, tmp_path: Path, monkeypatch):
        legacy_dir = tmp_path / "docs" / "fitness"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "code-quality.md").write_text("legacy", encoding="utf-8")
        calls = []

        class Adapter:
            def __init__(self, **_kwargs):
                calls.append("constructed")

            def on_before_stop(self, _context):
                raise AssertionError("legacy adapter must not run")

        monkeypatch.setattr("entrix.stop_gate.adapter.StopGateAdapter", Adapter)

        rc, output = _run({"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch)

        assert rc == 0
        assert output == ""
        assert calls == []

    def test_routes_root_harness_config_to_runner(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "harness.yaml"
        config_path.write_text("version: harness/v1\n")
        calls = {}

        class Runner:
            def __init__(self, path, **_kwargs):
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
            def __init__(self, path, **_kwargs):
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

    def test_routes_nested_harness_config_to_runner(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / ".harness" / "harness.yaml"
        config_path.parent.mkdir()
        config_path.write_text("version: harness/v1\n")

        class Runner:
            def __init__(self, path, **_kwargs):
                assert path == config_path

            def run(self, context):
                return type("Verdict", (), {"status": type("Status", (), {"value": "pass"})(), "summary": ""})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)

        rc, out = _run({"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch)

        assert rc == 0
        assert out == ""

    @pytest.mark.parametrize("failure_stage", ["init", "run"])
    def test_harness_error_blocks_stop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
    ) -> None:
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n")

        class Runner:
            def __init__(self, _path, **_kwargs):
                if failure_stage == "init":
                    raise RuntimeError("runner unavailable")

            def run(self, _context):
                raise ValueError("invalid harness")

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)

        rc, out = _run({"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch)

        assert rc == 0
        assert json.loads(out)["decision"] == "block"

    def test_state_store_error_blocks_configured_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n")
        monkeypatch.setattr(
            "entrix.stop_gate.hook.StopGateStateStore.load",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("state unavailable")),
        )

        rc, out = _run(
            {"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch
        )

        assert rc == 0
        assert json.loads(out)["decision"] == "block"
        assert "state unavailable" in json.loads(out)["reason"]

    def test_branch_detection_error_blocks_configured_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n")
        monkeypatch.setattr(
            "entrix.stop_gate.hook.derive_current_branch",
            lambda _workspace: (_ for _ in ()).throw(RuntimeError("git unavailable")),
        )

        rc, out = _run(
            {"session_id": "s1", "cwd": str(tmp_path)}, tmp_path, monkeypatch
        )

        assert rc == 0
        assert json.loads(out)["decision"] == "block"
        assert "git unavailable" in json.loads(out)["reason"]

    def test_allow_when_no_harness_config(self, tmp_path: Path, monkeypatch):
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}
        rc, out = _run(payload, tmp_path, monkeypatch)
        assert rc == 0
        assert out == ""

    @pytest.mark.parametrize("status", ["fail", "blocked"])
    def test_stop_hook_active_reuses_failure_until_workspace_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
    ) -> None:
        """失败后不变更工作区时必须重用裁决，不能重新启动 Harness。"""
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
        calls = []

        class Runner:
            def __init__(self, _path, **_kwargs):
                pass

            def run(self, _context):
                calls.append("run")
                return type("Verdict", (), {"status": status, "summary": "Tests failed"})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)
        monkeypatch.setattr(
            "entrix.stop_gate.hook.workspace_fingerprint",
            lambda _workspace: "unchanged",
            raising=False,
        )
        state_dir = tmp_path / "stop-gate-state"
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}

        first_rc, first_out = _run(payload, tmp_path, monkeypatch, state_dir=state_dir)
        payload["stop_hook_active"] = True
        second_rc, second_out = _run(payload, tmp_path, monkeypatch, state_dir=state_dir)

        assert first_rc == 0
        assert json.loads(first_out)["decision"] == "block"
        assert second_rc == 0
        assert json.loads(second_out)["decision"] == "block"
        assert "未检测到代码变更" in json.loads(second_out)["reason"]
        assert calls == ["run"]

    def test_stop_hook_reruns_after_workspace_changes(self, tmp_path: Path, monkeypatch):
        """Claude 修复代码后，下一次 Stop 必须重新收集 Harness 证据。"""
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
        calls = []

        class Runner:
            def __init__(self, _path, **_kwargs):
                pass

            def run(self, _context):
                calls.append("run")
                return type("Verdict", (), {"status": "fail", "summary": "Tests failed"})()

        fingerprints = iter(["before", "before", "after"])
        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)
        monkeypatch.setattr(
            "entrix.stop_gate.hook.workspace_fingerprint",
            lambda _workspace: next(fingerprints),
            raising=False,
        )
        state_dir = tmp_path / "stop-gate-state"
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}

        _run(payload, tmp_path, monkeypatch, state_dir=state_dir)
        _run(payload, tmp_path, monkeypatch, state_dir=state_dir)
        _run(payload, tmp_path, monkeypatch, state_dir=state_dir)

        assert calls == ["run", "run"]

    def test_stop_hook_allows_stop_after_a_changed_workspace_passes(self, tmp_path: Path, monkeypatch):
        """A changed workspace must be revalidated and may then complete the Stop loop."""
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
        statuses = iter(
            [
                ("fail", "Tests failed"),
                ("pass", "Tests passed"),
                ("pass", "Tests passed again"),
            ]
        )
        calls = []

        class Runner:
            def __init__(self, _path, **_kwargs):
                pass

            def run(self, _context):
                calls.append("run")
                status, summary = next(statuses)
                return type("Verdict", (), {"status": status, "summary": summary})()

        fingerprints = iter(["before", "after", "after"])
        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)
        monkeypatch.setattr(
            "entrix.stop_gate.hook.workspace_fingerprint",
            lambda _workspace: next(fingerprints),
            raising=False,
        )
        state_dir = tmp_path / "stop-gate-state"
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}

        first_rc, first_out = _run(payload, tmp_path, monkeypatch, state_dir=state_dir)
        second_rc, second_out = _run(payload, tmp_path, monkeypatch, state_dir=state_dir)
        third_rc, third_out = _run(payload, tmp_path, monkeypatch, state_dir=state_dir)

        assert first_rc == 0
        assert json.loads(first_out)["decision"] == "block"
        assert second_rc == 0
        assert second_out == ""
        assert third_rc == 0
        assert third_out == ""
        assert calls == ["run", "run", "run"]

    def test_stop_hook_reruns_when_branch_changes(self, tmp_path: Path, monkeypatch):
        """A verdict for one branch cannot authorize the same files on another branch."""
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
        calls = []

        class Runner:
            def __init__(self, _path, **_kwargs):
                pass

            def run(self, context):
                calls.append(context["branch"])
                return type("Verdict", (), {"status": "fail", "summary": "Tests failed"})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)
        monkeypatch.setattr(
            "entrix.stop_gate.hook.workspace_fingerprint",
            lambda _workspace: "workspace",
            raising=False,
        )
        state_dir = tmp_path / "stop-gate-state"
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}

        _run({**payload, "branch": "main"}, tmp_path, monkeypatch, state_dir=state_dir)
        _run({**payload, "branch": "release"}, tmp_path, monkeypatch, state_dir=state_dir)

        assert calls == ["main", "release"]

    def test_stop_hook_reruns_when_base_ref_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
        calls = []

        class Runner:
            def __init__(self, _path, **_kwargs):
                pass

            def run(self, context):
                calls.append(context["base_ref"])
                return type("Verdict", (), {"status": "fail", "summary": "Tests failed"})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)
        monkeypatch.setattr(
            "entrix.stop_gate.hook.workspace_fingerprint",
            lambda _workspace: "workspace",
        )
        state_dir = tmp_path / "stop-gate-state"
        payload = {"session_id": "s1", "cwd": str(tmp_path)}

        _run(payload, tmp_path, monkeypatch, state_dir=state_dir)
        run_stop_gate_hook(
            base_ref="origin/main",
            input_stream=io.StringIO(json.dumps(payload)),
            output_stream=io.StringIO(),
            state_dir=state_dir,
        )

        assert calls == [None, "origin/main"]

    def test_stop_hook_reruns_when_a_referenced_environment_value_changes(self, tmp_path: Path, monkeypatch):
        """Environment-gated checks cannot reuse a verdict after their switch changes."""
        (tmp_path / "harness.yaml").write_text(
            "version: harness/v1\nwhen:\n  env:\n    ENTRIX_GATE_TOGGLE: 'on'\n",
            encoding="utf-8",
        )
        calls = []

        class Runner:
            def __init__(self, _path, **_kwargs):
                pass

            def run(self, _context):
                calls.append("run")
                return type("Verdict", (), {"status": "fail", "summary": "Tests failed"})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)
        monkeypatch.setattr(
            "entrix.stop_gate.hook.workspace_fingerprint",
            lambda _workspace: "workspace",
            raising=False,
        )
        state_dir = tmp_path / "stop-gate-state"
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}

        monkeypatch.setenv("ENTRIX_GATE_TOGGLE", "off")
        _run(payload, tmp_path, monkeypatch, state_dir=state_dir)
        monkeypatch.setenv("ENTRIX_GATE_TOGGLE", "on")
        _run(payload, tmp_path, monkeypatch, state_dir=state_dir)

        assert calls == ["run", "run"]

    def test_stop_hook_reruns_when_gate_environment_value_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "harness.yaml").write_text(
            "version: harness/v1\ngate_policies:\n"
            "  - name: CI only\n    severity: hard\n"
            "    when:\n      env:\n        ENTRIX_GATE_TOGGLE: 'on'\n"
            "    rule: {evidence_id: tests, condition: 'status == \"pass\"'}\n",
            encoding="utf-8",
        )
        calls = []

        class Runner:
            def __init__(self, _path, **_kwargs):
                pass

            def run(self, _context):
                calls.append("run")
                return type("Verdict", (), {"status": "fail", "summary": "Tests failed"})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)
        monkeypatch.setattr(
            "entrix.stop_gate.hook.workspace_fingerprint",
            lambda _workspace: "workspace",
        )
        state_dir = tmp_path / "stop-gate-state"
        payload = {"session_id": "s1", "cwd": str(tmp_path)}

        monkeypatch.setenv("ENTRIX_GATE_TOGGLE", "off")
        _run(payload, tmp_path, monkeypatch, state_dir=state_dir)
        monkeypatch.setenv("ENTRIX_GATE_TOGGLE", "on")
        _run(payload, tmp_path, monkeypatch, state_dir=state_dir)

        assert calls == ["run", "run"]

    def test_env_var_disables_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
        monkeypatch.setenv("ENTRIX_STOP_GATE_DISABLED", "1")
        payload = {"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "Stop"}
        rc, out = _run(payload, tmp_path, monkeypatch)
        assert rc == 0
        assert out == ""
        assert "disabled" in capsys.readouterr().err.lower()

    def test_block_on_hard_gate_failure(self, tmp_path: Path, monkeypatch):
        (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")

        class Runner:
            def __init__(self, _path):
                pass

            def run(self, _context):
                return type("Verdict", (), {"status": "fail", "summary": "Fitness failed"})()

        monkeypatch.setattr("entrix.stop_gate.runner.HarnessRunner", Runner)
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


def test_main_blocks_unexpected_error_in_configured_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "harness.yaml").write_text("version: harness/v1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "entrix.stop_gate.hook.run_stop_gate_hook",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )

    assert stop_gate_main([]) == 0

    output = capsys.readouterr()
    assert json.loads(output.out)["decision"] == "block"
    assert "unexpected" in output.out


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
def test_shell_wrapper_blocks_when_no_runner_is_available(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    script = Path(__file__).parents[2] / "hooks" / "stop-gate.sh"
    environment = os.environ.copy()
    environment["PATH"] = str(tmp_path)
    environment.pop("CLAUDE_PLUGIN_ROOT", None)
    environment.pop("ENTRIX_STOP_GATE_DISABLED", None)

    result = subprocess.run(
        [bash, str(script)],
        input="{}",
        encoding="utf-8",  # Fix Windows encoding issue
        errors="replace",  # Replace invalid characters instead of failing
        capture_output=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "block"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
def test_shell_wrapper_audits_explicit_disable(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    script = Path(__file__).parents[2] / "hooks" / "stop-gate.sh"
    environment = os.environ.copy()
    environment["PATH"] = str(tmp_path)
    environment["ENTRIX_STOP_GATE_DISABLED"] = "1"

    result = subprocess.run(
        [bash, str(script)],
        input="{}",
        encoding="utf-8",  # Fix Windows encoding issue
        errors="replace",  # Replace invalid characters instead of failing
        capture_output=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert "disabled" in result.stderr.lower()
