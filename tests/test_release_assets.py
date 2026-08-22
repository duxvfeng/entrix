from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_release_assets import asset_name, build_manifest, main, target_name


def test_release_target_names() -> None:
    assert target_name("Windows", "AMD64") == "windows-amd64"
    assert target_name("Linux", "x86_64") == "linux-amd64"
    assert target_name("Linux", "aarch64") == "linux-arm64"
    assert target_name("Darwin", "x86_64") == "macos-amd64"
    assert target_name("Darwin", "arm64") == "macos-arm64"


def test_release_target_names_reject_unknown_platform() -> None:
    with pytest.raises(ValueError, match="unsupported release target"):
        target_name("FreeBSD", "x86_64")


def test_asset_name_includes_version_and_windows_extension() -> None:
    assert asset_name("0.1.22", "windows-amd64") == "entrix-0.1.22-windows-amd64.exe"
    assert asset_name("0.1.22", "linux-amd64") == "entrix-0.1.22-linux-amd64"


def test_manifest_contains_sha256_and_download_url(tmp_path: Path) -> None:
    binary = tmp_path / "entrix-0.1.22-linux-amd64"
    binary.write_bytes(b"binary")

    manifest = build_manifest("0.1.22", "https://github.com/duxvfeng/entrix", [binary])

    assert manifest["version"] == "0.1.22"
    assert manifest["assets"][0]["target"] == "linux-amd64"
    assert manifest["assets"][0]["sha256"] == hashlib.sha256(b"binary").hexdigest()
    assert manifest["assets"][0]["url"].endswith(
        "/releases/download/v0.1.22/" + binary.name
    )


def test_manifest_can_be_serialized_without_path_objects(tmp_path: Path) -> None:
    binary = tmp_path / "entrix-0.1.22-linux-amd64"
    binary.write_bytes(b"binary")

    payload = build_manifest("0.1.22", "https://github.com/duxvfeng/entrix", [binary])

    assert json.loads(json.dumps(payload))["assets"][0]["filename"] == binary.name


def test_cli_writes_sha256_sidecars_and_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "entrix-0.1.22-linux-amd64"
    binary.write_bytes(b"binary")
    output = tmp_path / "release-manifest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_release_assets.py",
            "--version",
            "0.1.22",
            "--repository",
            "https://github.com/duxvfeng/entrix",
            "--input-dir",
            str(tmp_path),
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    assert (tmp_path / f"{binary.name}.sha256").read_text(encoding="ascii").startswith(
        hashlib.sha256(b"binary").hexdigest()
    )
    assert json.loads(output.read_text(encoding="utf-8"))["assets"][0]["filename"] == binary.name


@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is unavailable")
def test_cli_signs_manifest_and_checksum_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "entrix-0.1.22-linux-amd64"
    binary.write_bytes(b"binary")
    key = tmp_path / "signing.key"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key)],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "release-manifest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_release_assets.py",
            "--version",
            "0.1.22",
            "--repository",
            "https://github.com/duxvfeng/entrix",
            "--input-dir",
            str(tmp_path),
            "--output",
            str(output),
            "--signing-key",
            str(key),
        ],
    )

    assert main() == 0
    assert (tmp_path / "release-manifest.json.sig").is_file()
    assert (tmp_path / f"{binary.name}.sha256.sig").is_file()
