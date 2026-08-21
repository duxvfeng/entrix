from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
UNIX_BOOTSTRAP = ROOT / "bin" / "entrix-bootstrap.sh"
UNIX_ENTRYPOINT = ROOT / "bin" / "entrix"
WINDOWS_BOOTSTRAP = ROOT / "bin" / "entrix-bootstrap.ps1"
WINDOWS_ENTRYPOINT = ROOT / "bin" / "entrix.bat"
NODE_ENTRYPOINT = ROOT / "bin" / "entrix-bootstrap.mjs"
STOP_HOOK = ROOT / "hooks" / "stop-gate.sh"


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_release_asset(source_dir: Path, version: str, *, checksum: str | None = None) -> Path:
    binary = source_dir / f"entrix-{version}-linux-amd64"
    binary.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'fake-binary:%s\\n' \"$*\"\n"
        "exit \"${FAKE_BINARY_EXIT:-0}\"\n",
        encoding="utf-8",
    )
    _make_executable(binary)
    digest = checksum or hashlib.sha256(binary.read_bytes()).hexdigest()
    (source_dir / f"{binary.name}.sha256").write_text(f"{digest}  {binary.name}\n", encoding="ascii")
    return binary


def _write_fake_curl(tmp_path: Path, source_dir: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    log_path = tmp_path / "curl.log"
    curl = fake_bin / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        f"source_dir={json.dumps(str(source_dir))}\n"
        f"log_path={json.dumps(str(log_path))}\n"
        "url=''\n"
        "output=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    -o) output=$2; shift 2 ;;\n"
        "    -*) shift ;;\n"
        "    *) url=$1; shift ;;\n"
        "  esac\n"
        "done\n"
        "asset=${url##*/}\n"
        "printf '%s\\n' \"$asset\" >> \"$log_path\"\n"
        "cp \"$source_dir/$asset\" \"$output\"\n",
        encoding="utf-8",
    )
    _make_executable(curl)
    return fake_bin, log_path


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_downloads_verifies_caches_and_forwards_args(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.9"
    source_dir = tmp_path / "release"
    source_dir.mkdir()
    _write_release_asset(source_dir, version)
    fake_bin, log_path = _write_fake_curl(tmp_path, source_dir)
    cache_home = tmp_path / "cache"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "XDG_CACHE_HOME": str(cache_home),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_RELEASE_BASE_URL": "https://release.invalid/assets",
        }
    )

    first = subprocess.run(
        [bash, str(UNIX_BOOTSTRAP), "serve", "--flag", "value"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert first.returncode == 0
    assert first.stdout.strip() == "fake-binary:serve --flag value"
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "entrix-9.9.9-linux-amd64",
        "entrix-9.9.9-linux-amd64.sha256",
    ]

    source_dir.rename(tmp_path / "release-offline")
    second = subprocess.run(
        [bash, str(UNIX_ENTRYPOINT), "stop-gate", "payload"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert second.returncode == 0
    assert second.stdout.strip() == "fake-binary:stop-gate payload"
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_rejects_checksum_mismatch(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.10"
    source_dir = tmp_path / "release"
    source_dir.mkdir()
    _write_release_asset(source_dir, version, checksum="0" * 64)
    fake_bin, _ = _write_fake_curl(tmp_path, source_dir)
    cache_home = tmp_path / "cache"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "XDG_CACHE_HOME": str(cache_home),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_RELEASE_BASE_URL": "https://release.invalid/assets",
        }
    )

    result = subprocess.run(
        [bash, str(UNIX_BOOTSTRAP), "serve"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode != 0
    assert "SHA-256" in result.stderr
    assert not list((cache_home / "entrix" / "bin" / version).rglob("entrix-*"))


def test_unix_entrypoint_is_python_free() -> None:
    content = UNIX_ENTRYPOINT.read_text(encoding="utf-8")
    assert "python" not in content.lower()
    assert "entrix-bootstrap.sh" in content


def test_node_entrypoint_is_platform_dispatcher() -> None:
    content = NODE_ENTRYPOINT.read_text(encoding="utf-8")
    assert 'process.platform === "win32"' in content
    assert "entrix-bootstrap.ps1" in content
    assert "entrix-bootstrap.sh" in content
    assert "spawnSync" in content


def test_windows_launcher_contract() -> None:
    bootstrap = WINDOWS_BOOTSTRAP.read_text(encoding="utf-8")
    entrypoint = WINDOWS_ENTRYPOINT.read_text(encoding="utf-8")
    assert "RuntimeInformation.ProcessArchitecture" in bootstrap
    assert "Architecture::X64" in bootstrap
    assert "Architecture::Amd64" not in bootstrap
    assert "LOCALAPPDATA" in bootstrap
    assert "entrix\\bin" in bootstrap
    assert "Invoke-WebRequest" in bootstrap
    assert "Get-FileHash" in bootstrap
    assert "Algorithm SHA256" in bootstrap
    assert "ValueFromRemainingArguments" in bootstrap
    assert "LASTEXITCODE" in bootstrap
    assert "powershell.exe" in entrypoint
    assert "entrix-bootstrap.ps1" in entrypoint


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher smoke test")
def test_node_entrypoint_starts_windows_bootstrap_and_forwards_args() -> None:
    node = shutil.which("node")
    assert node is not None
    with tempfile.TemporaryDirectory() as temp_dir:
        fake_binary = Path(temp_dir) / "fake-entrix.cmd"
        fake_binary.write_text(
            "@echo off\n"
            "echo fake-binary:%*\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["ENTRIX_BINARY_PATH"] = str(fake_binary)

        result = subprocess.run(
            [node, str(NODE_ENTRYPOINT), "stop-gate", "payload"],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "fake-binary:stop-gate payload"


def test_plugin_manifest_uses_binary_launcher() -> None:
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    server = manifest["mcpServers"]["entrix"]
    assert server["command"] == "node"
    assert server["args"] == ["${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs", "serve"]


def test_plugin_stop_hooks_use_plugin_root_launcher() -> None:
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    hook_configs = [
        manifest["hooks"],
        json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")),
    ]

    for config in hook_configs:
        stop_config = config if "Stop" in config else config["hooks"]
        hook = stop_config["Stop"][0]["hooks"][0]
        assert hook["command"] == "node"
        assert hook["args"] == [
            "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs",
            "stop-gate",
        ]
        assert "stop-gate.sh" not in hook["command"]
        assert "./hooks/" not in hook["command"]


def test_entrix_skill_defaults_to_simplified_chinese() -> None:
    skill = (ROOT / "skills" / "entrix" / "SKILL.md").read_text(encoding="utf-8")

    assert "默认使用简体中文回答用户" in skill
    assert "面向用户的解释、结论、错误说明和建议使用中文" in skill
    assert "代码、命令、路径、标识符、JSON 字段名和原始工具输出保持原样" in skill
    assert "用户明确要求英文时，再使用英文回答" in skill


def test_plugin_versions_match_package_version() -> None:
    package_version = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert package_version == "0.1.24"
    assert plugin["version"] == package_version
    assert marketplace["plugins"][0]["version"] == package_version
    assert plugin["mcpServers"]["entrix"]["env"]["ENTRIX_BINARY_VERSION"] == package_version
    assert plugin["hooks"]["Stop"][0]["hooks"][0]["env"]["ENTRIX_BINARY_VERSION"] == package_version
    assert marketplace["plugins"][0]["release"]["asset_prefix"] == f"entrix-{package_version}-"


def test_stop_hook_prefers_plugin_binary_and_fails_closed() -> None:
    content = STOP_HOOK.read_text(encoding="utf-8")
    plugin_index = content.index("CLAUDE_PLUGIN_ROOT")
    path_index = content.index("command -v entrix")
    uvx_index = content.index("command -v uvx")
    python_index = content.index("command -v python3")
    assert plugin_index < path_index < uvx_index < python_index
    assert '"decision":"block"' in content
    assert "ENTRIX_STOP_GATE_DISABLED" in content


def test_docs_describe_python_free_installation() -> None:
    docs = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/local-plugin-install.md", ".github/workflows/README.md")
    )
    for phrase in ("SHA-256", "ENTRIX_BINARY_PATH", "pip install entrix[mcp]"):
        assert phrase in docs
