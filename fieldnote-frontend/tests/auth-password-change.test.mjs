import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const source = fileURLToPath(new URL("../src/auth/passwordChange.ts", import.meta.url));

async function loadPasswordChange() {
  const output = await mkdtemp(path.join(os.tmpdir(), "fieldnote-password-change-"));
  execFileSync(path.join(root, "node_modules/.bin/tsc"), [source, "--target", "ES2022", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--outDir", output], { stdio: "pipe" });
  return {
    module: await import(`${pathToFileURL(path.join(output, "passwordChange.js")).href}?${Date.now()}`),
    cleanup: () => rm(output, { recursive: true, force: true }),
  };
}

test("initial password change sends the password to the API and refreshes the cleared profile", async () => {
  const { module, cleanup } = await loadPasswordChange();
  try {
    const calls = [];
    let identity = { role: "viewer", mustChangePassword: true };
    await module.changeInitialPassword(
      "new-password-123",
      async (path, options) => {
        calls.push({ path, options });
        assert.deepEqual(identity, { role: "viewer", mustChangePassword: true });
        return { must_change_password: false };
      },
      async () => {
        identity = { role: "viewer", mustChangePassword: false };
      },
    );

    assert.deepEqual(calls, [{
      path: "/auth/change-password",
      options: { method: "POST", body: JSON.stringify({ password: "new-password-123" }) },
    }]);
    assert.deepEqual(identity, { role: "viewer", mustChangePassword: false });
  } finally {
    await cleanup();
  }
});

for (const response of [{}, null, { must_change_password: true }]) {
  test(`initial password change rejects unconfirmed response ${JSON.stringify(response)}`, async () => {
    const { module, cleanup } = await loadPasswordChange();
    try {
      let refreshCount = 0;

      await assert.rejects(
        module.changeInitialPassword(
          "new-password-123",
          async () => response,
          async () => {
            refreshCount += 1;
          },
        ),
        { message: "Zmiana hasła nie została potwierdzona przez usługę." },
      );

      assert.equal(refreshCount, 0);
    } finally {
      await cleanup();
    }
  });
}
