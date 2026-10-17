// Regenerate src/services/api/schema.d.ts from the local API's OpenAPI schema.
// Runs the Python app factory directly (no server needed). Set PYTHON to override the interpreter.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, "..");
const repo = resolve(frontend, "..");
const venv = process.platform === "win32" ? join(repo, ".venv", "Scripts", "python.exe") : join(repo, ".venv", "bin", "python");
const python = process.env.PYTHON || (existsSync(venv) ? venv : "python");

const code = [
  "import json",
  "from src.api.app import create_app",
  "from src.api.config import ApiConfig",
  "print(json.dumps(create_app(ApiConfig(port=8000, origins=('http://localhost',), token='x')).openapi(), indent=2))",
].join("\n");
const spec = execFileSync(python, ["-c", code], { cwd: repo, encoding: "utf8" });
const specPath = join(frontend, "openapi.json");
writeFileSync(specPath, spec);

const out = join(frontend, "src", "services", "api", "schema.d.ts");
mkdirSync(dirname(out), { recursive: true });
// Fields with defaults stay optional in request types; response types are made required in types.ts.
const cli = join(frontend, "node_modules", "openapi-typescript", "bin", "cli.js");
execFileSync(process.execPath, [cli, specPath, "-o", out, "--default-non-nullable=false"], { stdio: "inherit" });
console.log(`Wrote ${out}`);
