#!/usr/bin/env bash
# Download, verify, cache, and execute the Entrix release binary on Unix hosts.

set -uo pipefail

die() {
  echo "entrix bootstrap: $*" >&2
  exit 1
}

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || die "cannot locate launcher directory"
plugin_root="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$script_dir/.." && pwd)}"

if [ -n "${ENTRIX_BINARY_PATH:-}" ]; then
  binary_path="$ENTRIX_BINARY_PATH"
  [ -f "$binary_path" ] || die "ENTRIX_BINARY_PATH is not a file: $binary_path"
  [ -x "$binary_path" ] || die "ENTRIX_BINARY_PATH is not executable: $binary_path"
  exec "$binary_path" "$@"
fi

version="${ENTRIX_BINARY_VERSION:-}"
if [ -z "$version" ] && [ -f "$plugin_root/.claude-plugin/plugin.json" ]; then
  version="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    "$plugin_root/.claude-plugin/plugin.json" | head -n 1)"
fi
[ -n "$version" ] || die "cannot determine plugin binary version"

system_name="$(uname -s 2>/dev/null || true)"
machine_name="$(uname -m 2>/dev/null || true)"
case "$system_name:$machine_name" in
  Linux:x86_64|Linux:amd64) target="linux-amd64" ;;
  Linux:aarch64|Linux:arm64) target="linux-arm64" ;;
  Darwin:x86_64|Darwin:amd64) target="macos-amd64" ;;
  Darwin:arm64|Darwin:aarch64) target="macos-arm64" ;;
  *) die "unsupported release target: $system_name/$machine_name" ;;
esac

asset="entrix-${version}-${target}"
cache_home="${XDG_CACHE_HOME:-${HOME:-}/.cache}"
[ -n "$cache_home" ] || die "cannot determine a cache directory"
cache_dir="$cache_home/entrix/bin/$version/$target"
cached_binary="$cache_dir/$asset"
cached_checksum="$cached_binary.sha256"
mkdir -p "$cache_dir" || die "cannot create cache directory: $cache_dir"

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
    return
  fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
    return
  fi
  return 1
}

valid_cache() {
  [ -f "$cached_binary" ] && [ -f "$cached_checksum" ] || return 1
  expected="$(awk 'NF { print $1; exit }' "$cached_checksum" 2>/dev/null || true)"
  [ "${#expected}" -eq 64 ] || return 1
  actual="$(hash_file "$cached_binary" 2>/dev/null || true)"
  [ "$actual" = "$expected" ]
}

if valid_cache; then
  chmod 755 "$cached_binary" || die "cannot mark cached binary executable"
  exec "$cached_binary" "$@"
fi

lock_dir="$cache_dir/.lock"
lock_acquired=0
cleanup() {
  if [ "$lock_acquired" -eq 1 ]; then
    rmdir "$lock_dir" 2>/dev/null || true
  fi
  if [ -n "${download_dir:-}" ]; then
    rm -rf "$download_dir"
  fi
}
trap cleanup EXIT INT TERM

release_lock() {
  if [ "$lock_acquired" -eq 1 ]; then
    rmdir "$lock_dir" 2>/dev/null || true
    lock_acquired=0
  fi
}

for _attempt in $(seq 1 120); do
  if mkdir "$lock_dir" 2>/dev/null; then
    lock_acquired=1
    break
  fi
  if valid_cache; then
    chmod 755 "$cached_binary" || die "cannot mark cached binary executable"
    release_lock
    exec "$cached_binary" "$@"
  fi
  sleep 0.05
done
[ "$lock_acquired" -eq 1 ] || die "timed out waiting for cache lock"

if valid_cache; then
  chmod 755 "$cached_binary" || die "cannot mark cached binary executable"
  release_lock
  exec "$cached_binary" "$@"
fi

repository="${ENTRIX_RELEASE_REPOSITORY:-duxvfeng/entrix}"
base_url="${ENTRIX_RELEASE_BASE_URL:-https://github.com/$repository/releases/download/v$version}"
base_url="${base_url%/}"
download_dir="$(mktemp -d "$cache_dir/.download.XXXXXX" 2>/dev/null || true)"
[ -n "$download_dir" ] && [ -d "$download_dir" ] || die "cannot create download temp directory"
binary_tmp="$download_dir/$asset"
checksum_tmp="$download_dir/$asset.sha256"

download() {
  url="$1"
  destination="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$destination"
    return
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -q -O "$destination" "$url"
    return
  fi
  die "neither curl nor wget is available"
}

echo "downloading $asset for $target" >&2
download "$base_url/$asset" "$binary_tmp" || die "failed to download $asset"
download "$base_url/$asset.sha256" "$checksum_tmp" || die "failed to download checksum for $asset"

expected="$(awk 'NF { print $1; exit }' "$checksum_tmp" 2>/dev/null || true)"
[ "${#expected}" -eq 64 ] || die "invalid SHA-256 file for $asset"
actual="$(hash_file "$binary_tmp" 2>/dev/null || true)"
[ -n "$actual" ] || die "no SHA-256 implementation available"
[ "$actual" = "$expected" ] || die "SHA-256 verification failed for $asset"

chmod 755 "$binary_tmp" || die "cannot mark downloaded binary executable"
mv "$binary_tmp" "$cached_binary" || die "cannot cache binary"
mv "$checksum_tmp" "$cached_checksum" || die "cannot cache checksum"
release_lock
exec "$cached_binary" "$@"
