import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import os from "node:os";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bundled = path.join(
  os.homedir(),
  ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3",
);
const candidates = [
  process.env.FLY_PYTHON,
  existsSync(bundled) ? bundled : null,
  "python3.13",
  "python3.12",
  "python3.11",
  "python3",
].filter(Boolean);
const python = candidates.find(
  (p) =>
    spawnSync(p, [
      "-c",
      "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)",
    ]).status === 0,
);
if (!python) {
  console.error("Install Python 3.11 or newer, or set FLY_PYTHON.");
  process.exit(1);
}
function run(command, args) {
  const r = spawnSync(command, args, { cwd: root, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status || 1);
}
console.log(
  "First setup downloads ~2 GB of public data and model weights. No API key required.",
);
if (!existsSync(path.join(root, ".venv"))) run(python, ["-m", "venv", ".venv"]);
const venv = path.join(
  root,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
run(venv, ["-m", "pip", "install", "-r", "requirements.txt"]);
run(venv, ["scripts/download_data.py"]);
run(venv, ["scripts/prepare_brain.py"]);
run(venv, ["-m", "server.vision"]);
if (
  existsSync(path.join(root, "data/listings.json")) &&
  !process.argv.includes("--no-seed")
)
  run(venv, ["scripts/seed_catalogue.py"]);
console.log("Ready. Start with: pnpm dev");
