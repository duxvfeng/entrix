#!/usr/bin/env python3
"""Exercise release launcher download, cache repair, and offline execution."""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import platform
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, env=env)


def _sign(path: Path, private_key: Path) -> None:
    result = _run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            f"{path}.sig",
            str(path),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "openssl failed to sign release asset")


def _prepare_release(release_dir: Path, plugin_root: Path, binary: Path, version: str, target: str) -> str:
    asset = f"entrix-{version}-{target}{'.exe' if target == 'windows-amd64' else ''}"
    asset_path = release_dir / asset
    shutil.copyfile(binary, asset_path)
    digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    checksum = release_dir / f"{asset}.sha256"
    checksum.write_text(f"{digest}  {asset}\n", encoding="ascii")

    private_key = plugin_root.parent / "release-signing.key"
    generated = _run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private_key),
        ]
    )
    if generated.returncode != 0:
        raise RuntimeError(generated.stderr.strip() or "openssl failed to generate release key")
    public_key = plugin_root / "security" / "release-public-key.pem"
    exported = _run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)])
    if exported.returncode != 0:
        raise RuntimeError(exported.stderr.strip() or "openssl failed to export release key")

    _sign(checksum, private_key)
    manifest = {
        "version": version,
        "assets": [
            {
                "version": version,
                "target": target,
                "filename": asset,
                "url": f"http://127.0.0.1/releases/{asset}",
                "sha256": digest,
            }
        ],
    }
    manifest_path = release_dir / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _sign(manifest_path, private_key)
    return asset


def _start_server(release_dir: Path) -> tuple[socketserver.ThreadingTCPServer, threading.Thread]:
    def handler(*args, **kwargs):
        return _QuietHandler(*args, directory=str(release_dir), **kwargs)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _run_launcher(launcher: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    if sys.platform == "win32":
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            raise RuntimeError("PowerShell is required for the Windows launcher smoke test")
        command = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(launcher), "--help"]
    else:
        bash = shutil.which("bash")
        if bash is None:
            raise RuntimeError("bash is required for the Unix launcher smoke test")
        command = [bash, str(launcher), "--help"]
    return _run(command, env=env)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--target", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.binary.is_file():
        raise SystemExit(f"binary does not exist: {args.binary}")
    if shutil.which("openssl") is None:
        raise SystemExit("OpenSSL is required for launcher smoke tests")

    with tempfile.TemporaryDirectory(prefix="entrix-launcher-smoke-") as temporary:
        root = Path(temporary)
        release_dir = root / "release"
        plugin_root = root / "plugin-root"
        (plugin_root / "bin").mkdir(parents=True)
        (plugin_root / "security").mkdir()
        shutil.copy(args.launcher.parent / "verify-release-signature.mjs", plugin_root / "bin")
        shutil.copy(args.launcher.parent / "verify-release-manifest.mjs", plugin_root / "bin")
        release_dir.mkdir()
        asset = _prepare_release(release_dir, plugin_root, args.binary, args.version, args.target)
        server, thread = _start_server(release_dir)
        cache_root = root / "cache"
        environment = os.environ.copy()
        environment.update(
            {
                "CLAUDE_PLUGIN_ROOT": str(plugin_root),
                "ENTRIX_BINARY_VERSION": args.version,
                "ENTRIX_RELEASE_BASE_URL": f"http://127.0.0.1:{server.server_address[1]}",
                "ENTRIX_DOWNLOAD_TIMEOUT_SECONDS": "30",
                "XDG_CACHE_HOME": str(cache_root),
                "LOCALAPPDATA": str(cache_root),
            }
        )

        first = _run_launcher(args.launcher, environment)
        if first.returncode != 0:
            raise SystemExit(first.stderr.strip() or first.stdout.strip() or "launcher download smoke failed")

        cache_dir = cache_root / "entrix" / "bin" / args.version / args.target
        cached_binary = cache_dir / asset
        cached_binary.write_bytes(cached_binary.read_bytes() + b"corrupt-cache")
        repaired = _run_launcher(args.launcher, environment)
        if repaired.returncode != 0:
            raise SystemExit(repaired.stderr.strip() or repaired.stdout.strip() or "launcher cache repair smoke failed")

        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        offline = _run_launcher(args.launcher, environment)
        if offline.returncode != 0:
            raise SystemExit(offline.stderr.strip() or offline.stdout.strip() or "launcher offline cache smoke failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
