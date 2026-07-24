import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";

const root = fileURLToPath(new URL("..", import.meta.url));
const temp = mkdtempSync(join(tmpdir(), "fieldnote-comparison-"));
try {
  execFileSync(join(root, "node_modules/.bin/tsc"), [
    "src/app/comparisonSelection.ts", "--target", "ES2022", "--module", "NodeNext",
    "--moduleResolution", "NodeNext", "--outDir", temp,
  ], { cwd: root, stdio: "pipe" });
  const module = await import(pathToFileURL(join(temp, "comparisonSelection.js")).href);
  const products = [
    { id: "lionelo__agia", benchmark_group: "light_stroller" },
    { id: "bugaboo__butterfly-2", benchmark_group: "light_stroller" },
    { id: "lionelo__amber-2w1", benchmark_group: "stroller_2in1" },
  ];
  const first = module.toggleComparisonSelection(new Set(), products[0], products);
  const sameGroup = module.toggleComparisonSelection(first, products[1], products);
  const otherGroup = module.toggleComparisonSelection(sameGroup, products[2], products);
  assert.deepEqual([...sameGroup], ["lionelo__agia", "bugaboo__butterfly-2"]);
  assert.deepEqual([...otherGroup], ["lionelo__agia", "bugaboo__butterfly-2"]);
  assert.equal(module.canCompareSelection(sameGroup), true);
  assert.equal(module.canCompareSelection(first), false);
  console.log("comparison_selection=PASS");
} finally {
  rmSync(temp, { recursive: true, force: true });
}
