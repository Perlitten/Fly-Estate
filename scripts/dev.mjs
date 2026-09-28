import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
if (!existsSync(path.join(root, "data/brain/weights.npz"))) {
  console.error("Run: pnpm setup");
  process.exit(1);
}
const python = path.join(
  root,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const children = [
  spawn(
    python,
    [
      "-m",
      "uvicorn",
      "server.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8000",
    ],
    { cwd: root, stdio: "inherit" },
  ),
  spawn(
    process.execPath,
    [
      path.join(root, "node_modules/vite/bin/vite.js"),
      ...process.argv.slice(2),
    ],
    { cwd: root, stdio: "inherit" },
  ),
];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const p of children) p.kill("SIGTERM");
  setTimeout(() => process.exit(code), 300);
}
for (const p of children) {
  p.on("error", (e) => {
    console.error(e.message);
    stop(1);
  });
  p.on("exit", (code) => stop(code || 0));
}
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());
