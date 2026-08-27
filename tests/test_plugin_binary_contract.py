from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
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


def _prepare_signed_plugin_root(tmp_path: Path) -> tuple[Path, Path]:
    plugin_root = tmp_path / "plugin-root"
    (plugin_root / "bin").mkdir(parents=True)
    (plugin_root / "security").mkdir()
    shutil.copy(ROOT / "bin" / "verify-release-signature.mjs", plugin_root / "bin")
    shutil.copy(ROOT / "bin" / "verify-release-manifest.mjs", plugin_root / "bin")
    private_key = tmp_path / "release-signing.key"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private_key),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            str(private_key),
            "-pubout",
            "-out",
            str(plugin_root / "security" / "release-public-key.pem"),
        ],
        check=True,
        capture_output=True,
    )
    return plugin_root, private_key


def _sign_file(path: Path, private_key: Path) -> None:
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(path) + ".sig",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _write_release_asset(
    source_dir: Path,
    version: str,
    *,
    checksum: str | None = None,
    private_key: Path,
    target: str = "linux-amd64",
) -> Path:
    suffix = ".exe" if target == "windows-amd64" else ""
    binary = source_dir / f"entrix-{version}-{target}{suffix}"
    binary.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'fake-binary:%s\\n' \"$*\"\n"
        "exit \"${FAKE_BINARY_EXIT:-0}\"\n",
        encoding="utf-8",
    )
    _make_executable(binary)
    digest = checksum or hashlib.sha256(binary.read_bytes()).hexdigest()
    (source_dir / f"{binary.name}.sha256").write_text(f"{digest}  {binary.name}\n", encoding="ascii")
    _sign_file(source_dir / f"{binary.name}.sha256", private_key)
    manifest = {
        "version": version,
        "assets": [
            {
                "version": version,
                "target": target,
                "filename": binary.name,
                "url": f"https://release.invalid/assets/{binary.name}",
                "sha256": digest,
            }
        ],
    }
    manifest_path = source_dir / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _sign_file(manifest_path, private_key)
    return binary


def _host_target() -> str:
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "macos-arm64" if machine in {"arm64", "aarch64"} else "macos-amd64"
    if sys.platform == "linux":
        return "linux-arm64" if machine in {"arm64", "aarch64"} else "linux-amd64"
    return "windows-amd64"


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
@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_downloads_verifies_caches_and_forwards_args(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.9"
    target = _host_target()
    source_dir = tmp_path / "release"
    source_dir.mkdir()
    plugin_root, private_key = _prepare_signed_plugin_root(tmp_path)
    _write_release_asset(source_dir, version, private_key=private_key, target=target)
    fake_bin, log_path = _write_fake_curl(tmp_path, source_dir)
    cache_home = tmp_path / "cache"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "XDG_CACHE_HOME": str(cache_home),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_RELEASE_BASE_URL": "https://release.invalid/assets",
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
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
        f"entrix-9.9.9-{target}",
        f"entrix-9.9.9-{target}.sha256",
        f"entrix-9.9.9-{target}.sha256.sig",
        "release-manifest.json",
        "release-manifest.json.sig",
    ]

    cached_binary = cache_home / "entrix" / "bin" / version / target / f"entrix-{version}-{target}"
    cached_binary.write_bytes(cached_binary.read_bytes() + b"corrupt cache")
    repaired = subprocess.run(
        [bash, str(UNIX_ENTRYPOINT), "status"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert repaired.returncode == 0
    assert repaired.stdout.strip() == "fake-binary:status"
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 10

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
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 10


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_rejects_checksum_mismatch(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.10"
    target = _host_target()
    source_dir = tmp_path / "release"
    source_dir.mkdir()
    plugin_root, private_key = _prepare_signed_plugin_root(tmp_path)
    _write_release_asset(
        source_dir,
        version,
        checksum="0" * 64,
        private_key=private_key,
        target=target,
    )
    fake_bin, _ = _write_fake_curl(tmp_path, source_dir)
    cache_home = tmp_path / "cache"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "XDG_CACHE_HOME": str(cache_home),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_RELEASE_BASE_URL": "https://release.invalid/assets",
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
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


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_rejects_invalid_release_signature(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.11"
    target = _host_target()
    source_dir = tmp_path / "release"
    source_dir.mkdir()
    plugin_root, private_key = _prepare_signed_plugin_root(tmp_path)
    _write_release_asset(source_dir, version, private_key=private_key, target=target)
    (source_dir / "release-manifest.json.sig").write_bytes(b"invalid signature")
    fake_bin, _ = _write_fake_curl(tmp_path, source_dir)
    cache_home = tmp_path / "cache"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "XDG_CACHE_HOME": str(cache_home),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_RELEASE_BASE_URL": "https://release.invalid/assets",
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
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
    assert "signature" in result.stderr.lower()
    assert not list((cache_home / "entrix" / "bin" / version).rglob("entrix-*"))


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_runs_configured_quality_command_when_cache_lock_times_out(tmp_path: Path) -> None:
    """Stop Gate can use an explicit project quality command during cache outage."""
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.12"
    target = _host_target()
    plugin_root, _private_key = _prepare_signed_plugin_root(tmp_path)
    cache_dir = tmp_path / "cache" / "entrix" / "bin" / version / target
    (cache_dir / ".lock").mkdir(parents=True)
    marker = tmp_path / "maven-args.log"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_maven = fake_bin / "mvn"
    fake_maven.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" > {json.dumps(str(marker))}\n"
        "exit 0\n",
        encoding="utf-8",
    )
    _make_executable(fake_maven)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_BOOTSTRAP_LOCK_ATTEMPTS": "1",
            "ENTRIX_BOOTSTRAP_FALLBACK_COMMAND": "mvn -B -T1 -DskipTests validate",
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        }
    )

    result = subprocess.run(
        [bash, str(UNIX_BOOTSTRAP), "stop-gate"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8").strip() == "-B -T1 -DskipTests validate"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_does_not_use_quality_fallback_for_other_commands(tmp_path: Path) -> None:
    """The fallback must remain limited to Stop Gate execution."""
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.13"
    target = _host_target()
    plugin_root, _private_key = _prepare_signed_plugin_root(tmp_path)
    cache_dir = tmp_path / "cache" / "entrix" / "bin" / version / target
    (cache_dir / ".lock").mkdir(parents=True)
    environment = os.environ.copy()
    environment.update(
        {
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_BOOTSTRAP_LOCK_ATTEMPTS": "1",
            "ENTRIX_BOOTSTRAP_FALLBACK_COMMAND": "false",
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
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
    assert "timed out waiting for cache lock" in result.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_preserves_quality_command_failure(tmp_path: Path) -> None:
    """A failed fallback quality command must remain a failed quality result."""
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.14"
    target = _host_target()
    plugin_root, _private_key = _prepare_signed_plugin_root(tmp_path)
    cache_dir = tmp_path / "cache" / "entrix" / "bin" / version / target
    (cache_dir / ".lock").mkdir(parents=True)
    environment = os.environ.copy()
    environment.update(
        {
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_BOOTSTRAP_LOCK_ATTEMPTS": "1",
            "ENTRIX_BOOTSTRAP_FALLBACK_COMMAND": "exit 7",
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        }
    )

    result = subprocess.run(
        [bash, str(UNIX_BOOTSTRAP), "stop-gate"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 7


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is unavailable")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix launcher tests not supported on Windows")
def test_unix_launcher_reclaims_stale_cache_lock(tmp_path: Path) -> None:
    """An abandoned lock must not prevent a later bootstrap from repairing its cache."""
    bash = shutil.which("bash")
    assert bash is not None
    version = "9.9.16"
    target = _host_target()
    source_dir = tmp_path / "release"
    source_dir.mkdir()
    plugin_root, private_key = _prepare_signed_plugin_root(tmp_path)
    _write_release_asset(source_dir, version, private_key=private_key, target=target)
    fake_bin, _log_path = _write_fake_curl(tmp_path, source_dir)
    cache_dir = tmp_path / "cache" / "entrix" / "bin" / version / target
    lock_dir = cache_dir / ".lock"
    lock_dir.mkdir(parents=True)
    stale_time = time.time() - 3600
    os.utime(lock_dir, (stale_time, stale_time))
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_RELEASE_BASE_URL": "https://release.invalid/assets",
            "ENTRIX_BOOTSTRAP_LOCK_ATTEMPTS": "1",
            "ENTRIX_BOOTSTRAP_STALE_LOCK_SECONDS": "60",
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        }
    )

    result = subprocess.run(
        [bash, str(UNIX_BOOTSTRAP), "serve"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "fake-binary:serve"


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
    assert "release-manifest.json.sig" in bootstrap
    assert "checksum signature verification failed" in bootstrap
    assert "Test-Manifest" in bootstrap
    assert "powershell.exe" in entrypoint
    assert "entrix-bootstrap.ps1" in entrypoint


def test_windows_launcher_replaces_existing_cache_files_before_install() -> None:
    bootstrap = WINDOWS_BOOTSTRAP.read_text(encoding="utf-8")

    assert "function Install-CacheFile" in bootstrap
    assert "Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction Stop" in bootstrap
    assert "Move-Item -LiteralPath $Source -Destination $Destination -Force -ErrorAction Stop" in bootstrap
    assert bootstrap.count("Install-CacheFile ") == 5


def test_bootstraps_define_explicit_quality_fallback_contract() -> None:
    """Both platform launchers expose the same cache-lock quality fallback."""
    unix_bootstrap = UNIX_BOOTSTRAP.read_text(encoding="utf-8")
    windows_bootstrap = WINDOWS_BOOTSTRAP.read_text(encoding="utf-8")

    for content in (unix_bootstrap, windows_bootstrap):
        assert "ENTRIX_BOOTSTRAP_FALLBACK_COMMAND" in content
        assert "ENTRIX_BOOTSTRAP_LOCK_ATTEMPTS" in content
        assert "ENTRIX_BOOTSTRAP_STALE_LOCK_SECONDS" in content
        assert "stop-gate" in content


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher test")
def test_windows_launcher_runs_configured_quality_command_when_cache_lock_times_out(tmp_path: Path) -> None:
    """Windows Stop Gate can use an explicit project quality command during cache outage."""
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    version = "9.9.15"
    target = "windows-amd64"
    plugin_root, _private_key = _prepare_signed_plugin_root(tmp_path)
    cache_home = tmp_path / "cache"
    cache_dir = cache_home / "entrix" / "bin" / version / target
    (cache_dir / ".lock").mkdir(parents=True)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    marker = tmp_path / "maven-args.log"
    fake_maven = fake_bin / "mvn.cmd"
    fake_maven.write_text(
        f'@echo off\n>"{marker}" echo %*\nexit /b 0\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "LOCALAPPDATA": str(cache_home),
            "ENTRIX_BINARY_VERSION": version,
            "ENTRIX_BOOTSTRAP_LOCK_ATTEMPTS": "1",
            "ENTRIX_BOOTSTRAP_FALLBACK_COMMAND": "mvn -B -T1 -DskipTests validate",
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        }
    )

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WINDOWS_BOOTSTRAP),
            "stop-gate",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert marker.read_text(encoding="utf-8").strip() == "-B -T1 -DskipTests validate"


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
    assert package_version == "0.1.25"
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


def test_commands_declare_bootstrap_calls() -> None:
    """斜杠命令必须存在、frontmatter 齐全，且统一经由插件启动器调用。"""
    expected_commands = {
        "init": "init",
        "run": "run --tier fast",
        "validate": "harness validate",
        "phase": "phase",
        "trust": "trust",
        "review-trigger": "review-trigger",
    }
    for name, subcommand in expected_commands.items():
        path = ROOT / "commands" / f"{name}.md"
        content = path.read_text(encoding="utf-8")

        frontmatter = content.split("---", 2)[1]
        assert "description:" in frontmatter, name
        assert "argument-hint:" in frontmatter, name
        assert "allowed-tools: Bash(node:*)" in frontmatter, name
        assert "${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs" in content, name
        assert subcommand in content, name
