import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const appPath = new URL("../src/app/App.tsx", import.meta.url);

test("run history UI reads durable job endpoints instead of static records", async () => {
  const source = await readFile(appPath, "utf8");
  assert.equal(source.includes("const RUNS ="), false);
  assert.match(source, /\/jobs\?limit=50&offset=\$\{offset\}/);
  assert.match(source, /\/jobs\/\$\{runId\}\/retry/);
  assert.match(source, /\/jobs\/\$\{runId\}\/cancel/);
  assert.match(source, /"\/jobs\/research"/);
});

test("history refresh preserves rows and ignores superseded responses", async () => {
  const source = await readFile(appPath, "utf8");
  assert.match(source, /const requestSequence = useRef\(0\)/);
  assert.match(source, /if \(sequence !== requestSequence\.current\) return/);
  assert.match(source, /loading && runs\.length === 0/);
  assert.match(source, /error && runs\.length > 0/);
});

test("history exposes durable total and load-more pagination", async () => {
  const source = await readFile(appPath, "utf8");
  assert.match(source, /runs\.length < total/);
  assert.match(source, /Wczytaj starsze/);
  assert.match(source, /append \? \[\.\.\.current, \.\.\.nextRuns/);
});

test("history renders durable diagnostics with safe fallbacks", async () => {
  const source = await readFile(appPath, "utf8");
  assert.match(source, /sourceCount\(run, "sources_failed"\)/);
  assert.match(source, /coverage\(run, "coverage_before"\)/);
  assert.match(source, /run\.retry_of/);
  assert.match(source, /run\.error/);
});

test("history UI includes empty state and lifecycle counter fields", async () => {
  const source = await readFile(appPath, "utf8");
  assert.match(source, /Brak zapisanych uruchomień/);
  assert.match(source, /sources_selected/);
  assert.match(source, /sources_failed/);
});

test("run pagination contract keeps an explicit total and offset", () => {
  const response = { total: 3, limit: 2, offset: 0, runs: [{ run_id: "one" }, { run_id: "two" }] };
  assert.equal(response.runs.length, 2);
  assert.equal(response.total > response.runs.length, true);
});

test("production navigation excludes the legacy integrations mock", async () => {
  const source = await readFile(appPath, "utf8");
  assert.equal(source.includes('{ id: "integracje"'), false);
  assert.match(source, /Legacy Figma integration mock intentionally excluded/);
  assert.equal(source.includes("Jan Kowalski"), false);
});

test("navigation routes are shared outside the monolithic app shell", async () => {
  const routesPath = new URL("../src/routes/navigation.ts", import.meta.url);
  const source = await readFile(routesPath, "utf8");
  assert.match(source, /parseFieldnoteRoute/);
  assert.match(source, /routeForPage/);
});
