// Real browser → API → PostgreSQL; only the explicit deterministic demo provider.
import assert from "node:assert/strict";
import { chromium } from "playwright";
import fs from "node:fs/promises";

const api = process.env.HARNESS_API_URL ?? "http://127.0.0.1:8001";
const ui = process.env.HARNESS_UI_URL ?? "http://127.0.0.1:5174";
const suffix = Date.now();
const ids = [];
for (let i = 0; i < 22; i++) {
  const response = await fetch(`${api}/runs`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({test_name:`P3 browser ${suffix} ${i}`, prompt:"Return JSON with count 3",
      model:"demo-json-v1", configuration_state:"approved",
      criteria:[{criterion_id:"valid_json",parameters:{},weight:100}]}),
  });
  assert.equal(response.status, 200);
  ids.push((await response.json()).id);
}
const summary = await (await fetch(`${api}/history/runs?limit=20`)).json();
assert.equal(summary.items.length, 20);
assert(summary.next_cursor);
assert(!("prompt" in summary.items[0]) && !("response" in summary.items[0]));

const browser = await chromium.launch({headless:true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? {
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  } : {})});
const page = await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];
page.on("pageerror", error => errors.push(error.message));
try {
  await page.goto(ui);
  await page.getByText("Backend ready",{exact:true}).waitFor();
  assert.equal(await page.locator(".saved-run-item").count(),20);
  await page.getByRole("button",{name:"Load more runs",exact:true}).click();
  await page.waitForFunction(() => document.querySelectorAll(".saved-run-item").length > 20);
  await page.getByRole("button",{name:new RegExp(`Load P3 browser ${suffix} 21,`)}).click();
  await page.getByRole("heading",{name:`P3 browser ${suffix} 21`,exact:true}).waitFor();
  const reviewer=page.getByLabel("Authenticated reviewer");
  await page.waitForFunction(() => [...document.querySelectorAll("input")].some(input => input.readOnly && input.value==="omar-local"));
  assert(await reviewer.getAttribute("readonly") !== null);
  await page.getByLabel("Rating (0–100)").fill("0");
  await page.getByLabel(/Rationale|Explanation/i).fill("Review <script>window.evidenceExecuted=true</script>");
  await page.getByRole("button",{name:/Save review/i}).click();
  await page.getByText(/Review saved as revision 1/).waitFor();
  assert.equal(await page.evaluate(() => window.evidenceExecuted),undefined);
  await page.getByLabel("Rating (0–100)").fill("80");
  await page.getByLabel(/Rationale|Explanation/i).fill("Revised opinion");
  await page.getByRole("button",{name:/Save review/i}).click();
  await page.getByText(/Review saved as revision 2/).waitFor();
  assert.equal((await (await fetch(`${api}/runs/${ids.at(-1)}`)).json()).score,100);
  const downloadPromise=page.waitForEvent("download");
  await page.getByRole("button",{name:"Export opened run",exact:true}).click();
  const download=await downloadPromise;
  const path=await download.path();
  const bundle=JSON.parse(await fs.readFile(path,"utf8"));
  assert.equal(bundle.schema_version,"4.0");
  assert.equal(bundle.runs[0].reviews.length,2);
  await page.locator('input[type="file"]').setInputFiles(path);
  await page.getByText("A run ID already exists. Strict import cannot overwrite evidence.",{exact:true}).waitFor();
  await page.getByRole("button",{name:"Compare with another run",exact:true}).click();
  await page.getByRole("heading",{name:/Compare/i}).waitFor();
  if (process.env.HARNESS_SCREENSHOT_PATH) await page.screenshot({path:process.env.HARNESS_SCREENSHOT_PATH,fullPage:true});
  assert.deepEqual(errors,[]);
  console.log("P3 browser passed: summary pages → load more → detail → server reviewer → append revisions → safe text → export → strict conflict → comparison.");
} finally { await browser.close(); }
