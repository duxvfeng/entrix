import { readFileSync } from "node:fs";

const [manifestPath, version, target, filename, checksum] = process.argv.slice(2);
if (!manifestPath || !version || !target || !filename || !checksum) {
  console.error(
    "usage: verify-release-manifest.mjs <manifest> <version> <target> <filename> <sha256>",
  );
  process.exit(2);
}

try {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const assets = Array.isArray(manifest.assets) ? manifest.assets : [];
  const asset = assets.find((entry) => entry && entry.filename === filename);
  const valid =
    manifest.version === version &&
    asset &&
    asset.version === version &&
    asset.target === target &&
    asset.filename === filename &&
    asset.sha256 === checksum;
  if (!valid) {
    console.error("release manifest does not match the requested asset");
    process.exit(1);
  }
} catch (error) {
  console.error(`release manifest validation unavailable: ${error.message}`);
  process.exit(1);
}
