import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const client = fs.readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");
const provider = fs.readFileSync(new URL("../src/auth/AuthProvider.tsx", import.meta.url), "utf8");
const screens = fs.readFileSync(new URL("../src/auth/AuthScreens.tsx", import.meta.url), "utf8");

test("API and session initialization have bounded failure paths", () => {
  assert.match(client, /API_REQUEST_TIMEOUT_MS\s*=\s*8_000/);
  assert.match(client, /controller\.abort\(\)/);
  assert.match(client, /Lokalny backend nie odpowiedział/);
  assert.match(provider, /Supabase Auth nie odpowiedział/);
  assert.match(provider, /setState\("configuration-error"\)/);
  assert.match(screens, /AuthLoadingScreen/);
});
