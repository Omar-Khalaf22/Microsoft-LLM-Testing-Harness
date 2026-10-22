// Requires the backend (demo provider) and frontend to be running; never uses a real API key.
import assert from "node:assert/strict";
import { chromium } from "playwright";
const browser = await chromium.launch({
  headless: true,
  channel: "chromium",
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
    ? {
        executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
        args: JSON.parse(process.env.PLAYWRIGHT_CHROMIUM_ARGS || "[]"),
      }
    : {}),
});
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "reduce",
});
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const name = `P2 browser ${Date.now()}`;
try {
  await page.goto(process.env.HARNESS_UI_URL ?? "http://localhost:5173");
  await page.getByText("Backend ready", { exact: true }).waitFor();
  await page
    .getByRole("textbox", { name: "Test name", exact: true })
    .fill(name);
  await page
    .getByRole("textbox", { name: "Testing objective" })
    .fill("Return a JSON object with count 3");
  await page
    .getByRole("textbox", { name: "Test prompt", exact: true })
    .fill("Return JSON with count equal to 3.");
  await page.getByLabel("Model", { exact: true }).fill("demo-json-v1");
  await page.getByText("System instructions", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "Base system instructions" })
    .fill("Return precise JSON.");
  await page
    .getByRole("textbox", { name: "Additional system instructions" })
    .fill("Use numeric count.");
  await page
    .getByRole("button", { name: "Generate criteria", exact: true })
    .click();
  await page
    .getByText("Demo suggestions · no LLM request was made.", { exact: false })
    .waitFor();
  assert(
    await page
      .getByRole("button", { name: "Run and save test", exact: true })
      .isDisabled(),
  );
  const objectRow = page
    .locator(".criterion-editor")
    .filter({ has: page.getByText(/JSON object/i, { exact: true }) });
  // Reject one suggestion, then add an implemented structured criterion manually.
  await objectRow.getByRole("button", { name: /Remove/ }).click();
  await page
    .getByLabel("Add a supported criterion")
    .selectOption("json_field_type");
  await page
    .getByRole("button", { name: "Add criterion", exact: true })
    .click();
  const typeRow = page
    .locator(".criterion-editor")
    .filter({ has: page.getByText(/Json field type/i, { exact: true }) });
  await typeRow.getByRole("textbox").fill('{"field":"count","type":"integer"}');
  const approve = page.getByRole("checkbox", {
    name: /I reviewed and approve/,
  });
  await approve.check();
  await page
    .getByRole("button", { name: "Run and save test", exact: true })
    .click();
  await page.getByRole("heading", { name, exact: true }).waitFor();
  await page.getByText("100.00 / 100.00", { exact: true }).waitFor();
  assert(!(await page.getByText("PASS", { exact: true }).count()));
  assert(!(await page.getByText("REVIEW", { exact: true }).count()));
  await page.reload();
  await page
    .getByRole("button", { name: new RegExp(`Load ${name},`) })
    .first()
    .click();
  await page.getByRole("heading", { name, exact: true }).waitFor();
  await page.getByRole("button", { name: "Back to Test", exact: true }).click();
  await page.getByText("System instructions", { exact: true }).click();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Base system instructions" })
      .inputValue(),
    "Return precise JSON.",
  );
  assert.equal(
    await page
      .getByRole("textbox", { name: "Additional system instructions" })
      .inputValue(),
    "Use numeric count.",
  );
  assert.equal(await page.locator(".criterion-editor").count(), 2);
  assert(
    !(await page
      .getByRole("checkbox", { name: /I reviewed and approve/ })
      .isChecked()),
  );
  await page.getByRole("checkbox", { name: /I reviewed and approve/ }).check();
  await page
    .getByRole("button", { name: "Run and save test", exact: true })
    .click();
  await page.getByRole("heading", { name, exact: true }).waitFor();
  await page.getByText(/Version 1 ·/).waitFor();
  await page.getByRole("button", { name: "Back to Test", exact: true }).click();
  await page.getByText("System instructions", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "Base system instructions" })
    .fill("Return precise JSON without Markdown.");
  await page.getByRole("checkbox", { name: /I reviewed and approve/ }).check();
  await page
    .getByRole("button", { name: "Run and save test", exact: true })
    .click();
  await page.getByRole("heading", { name, exact: true }).waitFor();
  await page.getByText(/Version 2 ·/).waitFor();
  if (process.env.HARNESS_SCREENSHOT_DIR) {
    await page.screenshot({
      path: `${process.env.HARNESS_SCREENSHOT_DIR}/desktop.png`,
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: `${process.env.HARNESS_SCREENSHOT_DIR}/mobile.png`,
      fullPage: true,
    });
  }
  assert.deepEqual(errors, []);
  console.log(
    "Browser flow passed: suggestions → edit/reject/add → approve → execute → save → reload → rerun → version change.",
  );
} finally {
  await browser.close();
}
