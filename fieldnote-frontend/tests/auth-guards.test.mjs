import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const source = fileURLToPath(new URL("../src/auth/guards.ts", import.meta.url));

async function loadGuards() {
  const output = await mkdtemp(path.join(os.tmpdir(), "fieldnote-auth-guards-"));
  execFileSync(path.join(root, "node_modules/.bin/tsc"), [source, "--target", "ES2022", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--outDir", output], { stdio: "pipe" });
  return { module: await import(`${pathToFileURL(path.join(output, "guards.js")).href}?${Date.now()}`), cleanup: () => rm(output, { recursive: true, force: true }) };
}

test("auth guard makes the first-password flow the only authenticated entrypoint", async () => {
  const { module, cleanup } = await loadGuards();
  try {
    assert.equal(module.screenForAuth("loading", null), "loading");
    assert.equal(module.screenForAuth("configured", null), "login");
    assert.equal(module.screenForAuth("configured", { role: "viewer", mustChangePassword: true }), "change-password");
    assert.equal(module.screenForAuth("configured", { role: "viewer", mustChangePassword: false }), "app");
    assert.equal(module.screenForAuth("configuration-error", null), "configuration-error");
  } finally { await cleanup(); }
});

test("role guards deny users administration and data writes until allowed", async () => {
  const { module, cleanup } = await loadGuards();
  try {
    const viewer = { role: "viewer", mustChangePassword: false };
    const analyst = { role: "analyst", mustChangePassword: false };
    const admin = { role: "admin", mustChangePassword: false };
    assert.equal(module.canAccessAdminUsers(viewer), false);
    assert.equal(module.canAccessAdminUsers(analyst), false);
    assert.equal(module.canAccessAdminUsers(admin), true);
    assert.equal(module.canWriteData(viewer), false);
    assert.equal(module.canWriteData(analyst), true);
    assert.equal(module.canWriteData({ ...admin, mustChangePassword: true }), false);
  } finally { await cleanup(); }
});
