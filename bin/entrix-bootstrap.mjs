import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const isWindows = process.platform === "win32";
const scriptName = isWindows ? "entrix-bootstrap.ps1" : "entrix-bootstrap.sh";
const command = isWindows ? "powershell.exe" : "bash";
const commandArgs = isWindows
  ? ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path.join(scriptDir, scriptName)]
  : [path.join(scriptDir, scriptName)];

const result = spawnSync(command, [...commandArgs, ...process.argv.slice(2)], {
  env: process.env,
  stdio: "inherit",
});

if (result.error) {
  console.error(`entrix launcher: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
