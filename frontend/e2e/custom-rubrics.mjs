// Real Vite UI → FastAPI → disposable PostgreSQL, with local fake providers.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";

const api = process.env.HARNESS_API_URL ?? "http://127.0.0.1:8001";
const ui = process.env.HARNESS_UI_URL ?? "http://127.0.0.1:5174";
const demo = JSON.parse(await readFile(new URL("../../examples/custom-rubrics-demo.json", import.meta.url), "utf8"));
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error" && message.text().includes("same key")) errors.push(message.text());
});

const button = (name) => page.getByRole("button", { name, exact: true });
const row = (index) => page.locator(".criterion-editor").nth(index);
const result = page.getByRole("region", { name: "Selected run result" });
const name = `Outlook browser ${Date.now()}`;
const miningName = `${name} mining`;

async function action(label, path, status) {
  const [completed] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === path),
    button(label).click(),
  ]);
  assert.equal(completed.status(), status, await completed.text());
  return completed.json();
}

async function apiGet(path) {
  const response = await fetch(`${api}${path}`);
  assert.equal(response.status, 200);
  return response.json();
}

async function fields(definition, label) {
  await page.getByLabel("Test Name", { exact: true }).fill(label);
  await page.getByLabel("Testing Objective", { exact: true }).fill(definition.objective);
  await page.getByLabel("Test Prompt", { exact: true }).fill(definition.prompt);
  if (definition.custom_system_prompt) {
    await page.getByText("System Instructions", { exact: true }).click();
    await page.getByLabel("Additional System Instructions", { exact: true }).fill(definition.custom_system_prompt);
  }
}

async function assertCustomRows(criteria) {
  assert.equal(await page.locator(".criterion-editor").count(), criteria.length);
  for (const [i, c] of criteria.entries()) {
    assert.equal(await row(i).getByLabel("Criterion Title", { exact: true }).inputValue(), c.parameters.title);
    assert.equal(await row(i).getByLabel("Scoring Instructions", { exact: true }).inputValue(), c.parameters.instructions);
    assert.equal(await row(i).getByLabel(/Judge-only reference/i).inputValue(), c.parameters.reference_evidence);
    assert.equal(await row(i).getByLabel(/Maximum points/i).inputValue(), String(c.weight));
  }
}

async function run(label = "Run Approved Version", path = "/executions", total = 75) {
  const plan = await action(label, path, 202);
  const id = plan.attempts[0].run_id;
  await page.locator(`[data-execution-id="${plan.execution_id}"]`)
    .getByText("1 completed · 0 failed · 0 running · 0 pending", { exact: true }).waitFor();
  await page.locator(`[data-run-id="${id}"]`)
    .getByText(`${total.toFixed(2)} / 100.00`, { exact: true }).waitFor();
  const stored = await apiGet(`/runs/${id}`);
  assert.equal(stored.score, total);
  return stored;
}

async function compare(left, right) {
  await button("Compare with Another Run").click();
  await page.getByLabel("Run A", { exact: true }).selectOption(left.id);
  await page.getByLabel("Run B", { exact: true }).selectOption(right.id);
  const table = page.getByRole("table", { name: "Criterion Points" });
  await table.waitFor();
  return table;
}

try {
  await page.goto(ui);
  await page.getByText("Backend ready", { exact: true }).waitFor();
  assert.deepEqual(await apiGet("/ready"), { status: "ready", schema: "0006_omar_storage" });
  const outlook = demo.outlook.definition;
  await fields(outlook, name);
  for (const [i, criterion] of outlook.criteria.entries()) {
    await button("Add Custom Criterion").click();
    const editor = row(i);
    await editor.getByLabel("Criterion Title", { exact: true }).fill(criterion.parameters.title);
    await editor.getByLabel("Scoring Instructions", { exact: true }).fill(criterion.parameters.instructions);
    await editor.getByLabel("Verifies factual claims").check();
    await editor.getByText("Enter reference evidence for factual verification.").waitFor();
    await editor.getByLabel(/Judge-only reference/i).fill(criterion.parameters.reference_evidence);
    await editor.getByLabel(/Maximum points/i).fill(String(criterion.weight));
  }
  await button("Add Custom Criterion").click();
  await row(3).getByText("Enter a criterion title.").waitFor();
  await row(3).getByRole("button", { name: /Remove/ }).click();
  await row(0).getByLabel(/Maximum points/i).fill("39.99");
  assert(await button("Save Draft").isDisabled());
  await row(0).getByLabel(/Maximum points/i).fill("40");
  await action("Generate Criteria", "/assistant/suggest-criteria", 200);
  await page.getByText("Demo suggestions · no LLM request was made.", { exact: false }).waitFor();
  assert(await page.locator(".criterion-editor").count() > 3);
  while (await page.locator(".criterion-editor").count() > 3)
    await page.locator(".criterion-editor").last().getByRole("button", { name: /Remove/ }).click();
  await assertCustomRows(outlook.criteria);
  const draft = await action("Save Draft", "/tests", 201);
  await page.getByText("Draft version 1", { exact: true }).waitFor();
  assert.equal(await button("Run Approved Version").count(), 0);

  await page.reload();
  await page.getByLabel("Saved Test", { exact: true }).selectOption(draft.test_id);
  await button("Open Version").click();
  await page.getByText("Draft version 1", { exact: true }).waitFor();
  await assertCustomRows(outlook.criteria);
  const versions = `/tests/${draft.test_id}/versions`;
  const approved = await action("Approve Version", `${versions}/1/approve`, 201);
  await page.getByText("Approved version 2", { exact: true }).waitFor();
  assert.deepEqual(approved.definition.criteria, draft.definition.criteria);
  await page.getByLabel("Approved target profile").selectOption("demo-outlook-a");
  await action("Request Interpretation Preview", "/previews", 201);
  await page.getByRole("heading", { name: "Original Task", exact: true }).waitFor();
  for (const field of ["Purpose", "Deliverable", "Constraints", "Success Conditions"])
    await page.locator(".preview-card").getByText(field, { exact: true }).waitFor();
  assert(await button("Run Approved Version").isDisabled());
  await page.getByLabel("I reviewed this interpretation").check();
  if (process.env.HARNESS_SCREENSHOT_DIR)
    await page.locator(".preview-card").screenshot({ path: join(process.env.HARNESS_SCREENSHOT_DIR, "preview.png") });
  const stronger = await run();
  assert.deepEqual(stronger.criteria.map((c) => c.score), [30, 35, 10]);
  await result.getByText("30.00 / 40.00", { exact: true }).waitFor();
  assert.equal(await result.getByText(/Model judge · demo-rubric-judge-v1/).count(), 3);
  assert.equal(await result.getByText("Scoring reference", { exact: true }).count(), 3);

  await page.getByLabel("Rating (0–100)").fill("82");
  await page.getByLabel("Rationale", { exact: true }).fill("Reviewer found the outlook clearly qualified.");
  await button("Save Review").click();
  await page.getByText(/Review saved as revision 1/).waitFor();
  assert.equal((await apiGet(`/runs/${stronger.id}`)).score, 75);

  await button("Back to Test").click();
  await page.getByLabel("Approved target profile").selectOption("demo-outlook-b");
  const weaker = await run("Run Approved Version", "/executions", 10);
  assert.deepEqual(weaker.criteria.map((c) => c.score), [10, 0, 0]);
  let table = await compare(stronger, weaker);
  await table.getByText("30.00 / 40.00", { exact: true }).waitFor();
  await table.getByText("10.00 / 40.00", { exact: true }).waitFor();
  await table.getByText("-20.00", { exact: true }).waitFor();
  await table.getByText("Target answer", { exact: true }).first().waitFor();
  await button("Close Comparison").click();
  await button("Back to Test").click();

  await row(0).getByLabel("Scoring Instructions", { exact: true })
    .fill(outlook.criteria[0].parameters.instructions + " Include explicit next steps.");
  const revisedDraft = await action("Save Draft", versions, 201);
  assert.equal(revisedDraft.test_version, 3);
  assert.deepEqual(revisedDraft.definition.criteria.map((r) => r.criterion_id),
    approved.definition.criteria.map((r) => r.criterion_id));
  await action("Approve Version", `${versions}/3/approve`, 201);
  await page.getByLabel("Approved target profile").selectOption("demo-outlook-a");
  const revised = await run();
  assert.equal(revised.metadata.test_version, 4);
  table = await compare(stronger, revised);
  await table.getByText("Rubric differs or is unavailable", { exact: true }).waitFor();
  assert.equal(await table.getByText("Rubric differs or is unavailable", { exact: true }).count(), 1);

  await page.reload();
  await page.getByRole("button", { name: new RegExp(`Load ${name},`) })
    .filter({ hasText: "Version 2" }).filter({ hasText: "75.00/100" }).click();
  await result.getByRole("heading", { name, exact: true }).waitFor();
  await page.getByText("82 / 100", { exact: true }).waitFor();
  const rerun = await run("Rerun Approved Version", `/runs/${stronger.id}/rerun`);
  assert.equal(rerun.metadata.test_version, 2);
  assert.equal(rerun.metadata.rerun_of_run_id, stronger.id);
  assert.deepEqual(rerun.criteria, stronger.criteria);
  if (process.env.HARNESS_SCREENSHOT_DIR) {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Close saved runs" }).click();
    await result.screenshot({ path: join(process.env.HARNESS_SCREENSHOT_DIR, "mobile-result.png") });
    await page.setViewportSize({ width: 1440, height: 1000 });
  }

  await button("Back to Test").click();
  await button("New Test").click();
  const mining = demo.mining.definition;
  await fields(mining, miningName);
  assert.equal(await page.getByRole("checkbox", { name: /legacy scoring/i }).count(), 0);
  const picker = page.getByRole("combobox", { name: "Add a Supported Criterion" });
  const options = page.getByRole("listbox", { name: "Supported criteria" });
  await picker.click();
  for (const check of ["Keyword coverage", "Prompt relevance", "Response length",
    "Sentence structure", "Forbidden terms", "Nonempty response"]) {
    await options.getByRole("option", { name: new RegExp(`^${check} ·`) }).waitFor();
  }
  await picker.fill("no matching criterion here");
  await page.getByText("No matching criteria.", { exact: true }).waitFor();
  assert(await button("Add Criterion").isDisabled());
  await picker.fill("JSON");
  assert((await options.getByRole("option").count()) > 1);
  await picker.press("End");
  await picker.pressSequentially(" schema");
  assert.equal(await options.getByRole("option").count(), 1);
  await picker.press("ArrowDown");
  await picker.press("Enter");
  assert.equal(await picker.inputValue(), "JSON schema");
  await button("Add Criterion").click();
  await row(0).getByRole("textbox").fill(JSON.stringify(mining.criteria[0].parameters));
  const miningDraft = await action("Save Draft", "/tests", 201);
  await action("Approve Version", `/tests/${miningDraft.test_id}/versions/1/approve`, 201);

  await button("Ordered Suites").click();
  await page.getByLabel("Suite name").fill(`${name} suite`);
  await page.getByLabel("Suite test", { exact: true }).selectOption(miningDraft.test_id);
  await button("Add to Suite").click();
  await page.getByLabel("Suite test", { exact: true }).selectOption(draft.test_id);
  await page.getByLabel("Suite test version", { exact: true }).selectOption("2");
  await button("Add to Suite").click();
  await button("Move item 2 up").click();
  const suite = await action("Save Suite", "/suites", 201);
  assert.deepEqual(suite.items.map((item) => item.test_id), [draft.test_id, miningDraft.test_id]);
  await page.getByLabel("Suite target profile").selectOption("demo-outlook-a");
  const execution = await action("Run Suite", "/executions", 202);
  await page.getByText("2 completed · 0 failed · 0 running · 0 pending", { exact: true }).waitFor();
  assert.deepEqual(execution.attempts.map((a) => a.test_version), [2, 2]);
  await button("View item 2 model 1 result").click();
  await result.getByRole("heading", { name: miningName, exact: true }).waitFor();
  await result.getByText("Built-in check · completed", { exact: true }).waitFor();
  assert.equal((await apiGet(`/runs/${execution.attempts[1].run_id}`)).score, 0);

  // Leave a run's view before progress arrives. The completion still appears in History.
  await button("View item 1 model 1 result").click();
  await result.getByRole("heading", { name, exact: true }).waitFor();
  let releaseProgress;
  const held = new Promise((resolve) => { releaseProgress = resolve; });
  const progressUrl = `${api}/executions/**`;
  await page.route(progressUrl, async (route) => {
    await held;
    await route.continue();
  });
  const backgroundRun = await action(
    "Rerun Approved Version", `/runs/${execution.attempts[0].run_id}/rerun`, 202,
  );
  await button("Ordered Suites").click();
  releaseProgress();
  await page.locator(`[data-execution-id="${backgroundRun.execution_id}"]`)
    .getByText("1 completed · 0 failed · 0 running · 0 pending", { exact: true }).waitFor();
  await page.getByRole("heading", { name: "Ordered Suites", exact: true }).waitFor();
  await page.unroute(progressUrl);
  assert.deepEqual(errors, []);
  console.log("Rubrics browser passed: authoring, suggestions, draft reopening, approval, preview, scoring, comparison, review, exact rerun, and ordered suite.");
} catch (error) {
  if (process.env.HARNESS_SCREENSHOT_DIR) {
    await page.screenshot({ path: join(process.env.HARNESS_SCREENSHOT_DIR, "failure.png") });
  }
  throw error;
} finally {
  await browser.close();
}
