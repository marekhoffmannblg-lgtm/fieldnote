import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));
const sourcePath = new URL("../src/app/runStatus.ts", import.meta.url);

async function loadRunStatusModule() {
  const outputDir = await mkdtemp(path.join(os.tmpdir(), "fieldnote-run-status-"));
  try {
    execFileSync(
      path.join(frontendRoot, "node_modules", ".bin", "tsc"),
      [
        fileURLToPath(sourcePath),
        "--target", "ES2022",
        "--module", "NodeNext",
        "--moduleResolution", "NodeNext",
        "--outDir", outputDir,
      ],
      { stdio: "pipe" },
    );
    return {
      module: await import(`${pathToFileURL(path.join(outputDir, "runStatus.js")).href}?${Date.now()}`),
      cleanup: () => rm(outputDir, { recursive: true, force: true }),
    };
  } catch (error) {
    await rm(outputDir, { recursive: true, force: true });
    throw error;
  }
}

test("terminal run classification never treats partial as success", async () => {
  const { module, cleanup } = await loadRunStatusModule();
  try {
    assert.equal(module.isRunSuccess({ status: "succeeded", pipeline_status: "success" }), true);
    assert.equal(module.isRunPartial({ status: "partial", pipeline_status: "partial" }), true);
    assert.equal(module.isRunSuccess({ status: "partial", pipeline_status: "partial" }), false);
  } finally {
    await cleanup();
  }
});

test("automatic reload requires a successful snapshot and an allowed terminal status", async () => {
  const { module, cleanup } = await loadRunStatusModule();
  try {
    assert.equal(module.shouldAutoReloadAfterRun({ status: "failed", pipeline_status: "failed", snapshot_updated: true }), false);
    assert.equal(module.shouldAutoReloadAfterRun({ status: "partial", pipeline_status: "partial", snapshot_updated: true }), true);
    assert.equal(module.shouldAutoReloadAfterRun({ status: "succeeded", pipeline_status: "success", snapshot_updated: true }), true);
  } finally {
    await cleanup();
  }
});
