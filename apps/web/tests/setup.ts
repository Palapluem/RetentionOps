import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

export default function setup() {
  const root = resolve(process.cwd(), "../..");
  execFileSync(
    "python",
    [
      "-m",
      "retentionops.cli",
      "events",
      "--root",
      resolve(root, "artifacts/e2e"),
      "--customers",
      "150",
    ],
    { cwd: root, stdio: "pipe" },
  );
}
