import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";

const root = fileURLToPath(new URL("..", import.meta.url));
const temp = mkdtempSync(join(tmpdir(), "fieldnote-category-"));
try {
  execFileSync(join(root, "node_modules/.bin/tsc"), [
    "src/app/categorySelection.ts", "src/app/offerSelection.ts", "--target", "ES2022", "--module", "NodeNext",
    "--moduleResolution", "NodeNext", "--outDir", temp,
  ], { cwd: root, stdio: "pipe" });
  const module = await import(pathToFileURL(join(temp, "categorySelection.js")).href);
  const selectionModule = await import(pathToFileURL(join(temp, "offerSelection.js")).href);
  const categories = [{ category_key: "stroller", label: "Wózki", benchmark_groups: [{ benchmark_group: "light_stroller", label: "Lekkie spacerówki" }] }];
  assert.equal(module.isValidCategorySelection(categories, "stroller", "light_stroller"), true);
  assert.equal(module.isValidCategorySelection(categories, "stroller", "stroller_3in1"), false);
  assert.equal(module.isValidCategorySelection(categories, "unknown", "light_stroller"), false);
  assert.equal(selectionModule.canSelectPreviewOffer(true, { selectable: true }), true);
  assert.equal(selectionModule.canSelectPreviewOffer(true, { selectable: false }), false);
  console.log("category_selection=PASS");
} finally {
  rmSync(temp, { recursive: true, force: true });
}
