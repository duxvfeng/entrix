#!/usr/bin/env python3
"""Build a versioned manifest and SHA-256 sidecars for release binaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

TARGETS = {
    ("Windows", "AMD64"): "windows-amd64",
    ("Linux", "x86_64"): "linux-amd64",
    ("Linux", "aarch64"): "linux-arm64",
    ("Darwin", "x86_64"): "macos-amd64",
    ("Darwin", "arm64"): "macos-arm64",
}
RELEASE_TARGETS = frozenset(TARGETS.values())


def target_name(system: str, machine: str) -> str:
    """Return the stable release target identifier for a runner platform."""
    try:
        return TARGETS[(system, machine)]
    except KeyError as error:
        raise ValueError(f"unsupported release target: {system}/{machine}") from error


def asset_name(version: str, target: str) -> str:
    """Return the canonical binary filename for a version and target."""
    if target not in RELEASE_TARGETS:
        raise ValueError(f"unsupported release target: {target}")
    suffix = ".exe" if target == "windows-amd64" else ""
    return f"entrix-{version}-{target}{suffix}"


def _target_from_filename(filename: str) -> str:
    for target in sorted(RELEASE_TARGETS, key=len, reverse=True):
        if filename.endswith(f"-{target}") or filename.endswith(f"-{target}.exe"):
            return target
    raise ValueError(f"cannot determine release target from filename: {filename}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(version: str, repository: str, binaries: list[Path]) -> dict:
    """Build the JSON-serializable release manifest for binary paths."""
    repository = repository.rstrip("/")
    assets = []
    for binary in sorted((Path(path) for path in binaries), key=lambda path: path.name):
        if not binary.is_file():
            raise FileNotFoundError(binary)
        target = _target_from_filename(binary.name)
        expected_name = asset_name(version, target)
        if binary.name != expected_name:
            raise ValueError(
                f"asset filename {binary.name!r} does not match version {version!r}; "
                f"expected {expected_name!r}"
            )
        assets.append(
            {
                "version": version,
                "target": target,
                "filename": binary.name,
                "url": f"{repository}/releases/download/v{version}/{binary.name}",
                "sha256": _sha256(binary),
            }
        )
    return {"version": version, "assets": assets}


def _write_sha256_sidecar(path: Path, digest: str) -> None:
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    expected_names = {
        asset_name(args.version, target)
        for target in RELEASE_TARGETS
    }
    binaries = [
        path for path in args.input_dir.iterdir() if path.is_file() and path.name in expected_names
    ]
    if not binaries:
        raise SystemExit(f"no release binaries found in {args.input_dir}")

    manifest = build_manifest(args.version, args.repository, binaries)
    for asset in manifest["assets"]:
        binary = args.input_dir / asset["filename"]
        _write_sha256_sidecar(binary, asset["sha256"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
