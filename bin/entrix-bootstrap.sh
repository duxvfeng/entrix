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
if [ -n "${XDG_CACHE_HOME:-}" ]; then
  cache_home="$XDG_CACHE_HOME"
elif [ -n "${HOME:-}" ]; then
  cache_home="$HOME/.cache"
else
  die "cannot determine a cache directory"
fi
cache_dir="$cache_home/entrix/bin/$version/$target"
cached_binary="$cache_dir/$asset"
cached_checksum="$cached_binary.sha256"
cached_checksum_signature="$cached_checksum.sig"
cached_manifest="$cache_dir/release-manifest.json"
cached_manifest_signature="$cached_manifest.sig"
public_key="$plugin_root/security/release-public-key.pem"
[ -f "$public_key" ] || die "release public key is missing: $public_key"
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

verify_signature() {
  file="$1"
  signature="$2"
  if command -v node >/dev/null 2>&1 && [ -f "$plugin_root/bin/verify-release-signature.mjs" ]; then
    node "$plugin_root/bin/verify-release-signature.mjs" "$public_key" "$file" "$signature" >/dev/null 2>&1
    return
  fi
  if command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 -verify "$public_key" -signature "$signature" "$file" >/dev/null 2>&1
    return
  fi
  return 1
}

verify_manifest() {
  [ -f "$plugin_root/bin/verify-release-manifest.mjs" ] || return 1
  command -v node >/dev/null 2>&1 || return 1
  node "$plugin_root/bin/verify-release-manifest.mjs" "$@" >/dev/null 2>&1
}

valid_cache() {
  [ -f "$cached_binary" ] && [ -f "$cached_checksum" ] || return 1
  [ -f "$cached_checksum_signature" ] && [ -f "$cached_manifest" ] || return 1
  [ -f "$cached_manifest_signature" ] || return 1
  expected="$(awk 'NF { print $1; exit }' "$cached_checksum" 2>/dev/null || true)"
  [ "${#expected}" -eq 64 ] || return 1
  actual="$(hash_file "$cached_binary" 2>/dev/null || true)"
  [ "$actual" = "$expected" ] || return 1
  verify_signature "$cached_manifest" "$cached_manifest_signature" || return 1
  verify_signature "$cached_checksum" "$cached_checksum_signature" || return 1
  verify_manifest "$cached_manifest" "$version" "$target" "$asset" "$expected"
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
checksum_signature_tmp="$checksum_tmp.sig"
manifest_tmp="$download_dir/release-manifest.json"
manifest_signature_tmp="$manifest_tmp.sig"

download() {
  url="$1"
  destination="$2"
  download_timeout="${ENTRIX_DOWNLOAD_TIMEOUT_SECONDS:-120}"
  case "$download_timeout" in
    ''|*[!0-9]*|0) die "ENTRIX_DOWNLOAD_TIMEOUT_SECONDS must be a positive integer" ;;
  esac
  if command -v curl >/dev/null 2>&1; then
    curl --fail --silent --show-error --location \
      --connect-timeout 10 --max-time "$download_timeout" \
      --retry 2 --retry-delay 1 "$url" -o "$destination"
    return
  fi
  if command -v wget >/dev/null 2>&1; then
    wget --quiet --timeout="$download_timeout" --tries=3 -O "$destination" "$url"
    return
  fi
  die "neither curl nor wget is available"
}

echo "downloading $asset for $target" >&2
download "$base_url/$asset" "$binary_tmp" || die "failed to download $asset"
download "$base_url/$asset.sha256" "$checksum_tmp" || die "failed to download checksum for $asset"
download "$base_url/$asset.sha256.sig" "$checksum_signature_tmp" || die "failed to download checksum signature for $asset"
download "$base_url/release-manifest.json" "$manifest_tmp" || die "failed to download release manifest"
download "$base_url/release-manifest.json.sig" "$manifest_signature_tmp" || die "failed to download release manifest signature"

verify_signature "$manifest_tmp" "$manifest_signature_tmp" || die "release manifest signature verification failed"
verify_signature "$checksum_tmp" "$checksum_signature_tmp" || die "checksum signature verification failed"

expected="$(awk 'NF { print $1; exit }' "$checksum_tmp" 2>/dev/null || true)"
[ "${#expected}" -eq 64 ] || die "invalid SHA-256 file for $asset"
verify_manifest "$manifest_tmp" "$version" "$target" "$asset" "$expected" || die "release manifest asset mismatch"
actual="$(hash_file "$binary_tmp" 2>/dev/null || true)"
[ -n "$actual" ] || die "no SHA-256 implementation available"
[ "$actual" = "$expected" ] || die "SHA-256 verification failed for $asset"

chmod 755 "$binary_tmp" || die "cannot mark downloaded binary executable"
mv "$binary_tmp" "$cached_binary" || die "cannot cache binary"
mv "$checksum_tmp" "$cached_checksum" || die "cannot cache checksum"
mv "$checksum_signature_tmp" "$cached_checksum_signature" || die "cannot cache checksum signature"
mv "$manifest_tmp" "$cached_manifest" || die "cannot cache release manifest"
mv "$manifest_signature_tmp" "$cached_manifest_signature" || die "cannot cache release manifest signature"
release_lock
exec "$cached_binary" "$@"
