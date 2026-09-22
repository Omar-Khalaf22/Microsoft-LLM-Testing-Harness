const form = document.querySelector("#test-form");
const runButton = document.querySelector("#run-button");
const suiteButton = document.querySelector("#suite-button");
const errorBox = document.querySelector("#error");
const temp = document.querySelector("#temperature");

temp.addEventListener("input", () => document.querySelector("#temp-value").textContent = temp.value);

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
}

function showResult(result) {
  document.querySelector("#empty-state").hidden = true;
  document.querySelector("#result").hidden = false;
  document.querySelector("#score").textContent = Math.round(result.score);
  const badge = document.querySelector("#badge");
  badge.textContent = result.passed ? "PASS" : "REVIEW";
  badge.className = `badge ${result.passed ? "" : "fail"}`;
  document.querySelector("#result-title").textContent = result.passed ? "Test passed" : "Needs review";
  document.querySelector("#metadata").textContent = `${result.model} · ${result.latency_ms} ms · ${result.provider}`;
  document.querySelector("#response").textContent = result.response;
  document.querySelector("#criteria").innerHTML = result.criteria.map(item => `
    <div class="criterion"><span class="mark ${item.passed ? "" : "fail"}">${item.passed ? "✓" : "×"}</span>
    <div><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.detail)}</p></div><span class="points">${item.score}</span></div>`).join("");
  document.querySelector("#json-result").textContent = JSON.stringify(result, null, 2);
}

async function loadHistory() {
  const response = await fetch("/api/results");
  const results = await response.json();
  document.querySelector("#history").innerHTML = results.length ? results.map(item => `
    <div class="history-row"><code>${escapeHtml(item.id.slice(0, 8))}</code><span>${escapeHtml(item.prompt.slice(0, 70))}</span>
    <span class="provider">${escapeHtml(item.provider)}</span><span class="history-score">${item.score}/100</span></div>`).join("") : '<p class="muted">No saved executions yet.</p>';
}

function formPayload() {
  return {
    prompt: document.querySelector("#prompt").value,
    expected_keywords: document.querySelector("#keywords").value,
    model: document.querySelector("#model").value,
    temperature: Number(temp.value),
    minimum_length: Number(document.querySelector("#minimum-length").value),
    minimum_sentences: Number(document.querySelector("#minimum-sentences").value),
    forbidden_terms: document.querySelector("#forbidden-terms").value
  };
}

async function executeTest(payload) {
  const response = await fetch("/api/run", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Test failed.");
  return result;
}

form.addEventListener("submit", async event => {
  event.preventDefault(); errorBox.textContent = ""; runButton.disabled = true; runButton.firstElementChild.textContent = "Executing…";
  try {
    const result = await executeTest(formPayload());
    showResult(result); await loadHistory();
  } catch (error) { errorBox.textContent = error.message; }
  finally { runButton.disabled = false; runButton.firstElementChild.textContent = "Run one test"; }
});

suiteButton.addEventListener("click", async () => {
  errorBox.textContent = ""; suiteButton.disabled = true; runButton.disabled = true;
  suiteButton.firstElementChild.textContent = "Running case 1 of 3…";
  const common = {temperature:0.2, minimum_length:120, minimum_sentences:3, forbidden_terms:"error, unavailable"};
  const cases = [
    {...common, model:"demo-strong-v1", prompt:"Explain how security and structured JSON improve an LLM testing pipeline.", expected_keywords:"security, JSON, testing, metadata"},
    {...common, model:"demo-partial-v1", prompt:"Describe authentication, privacy, and validation for stored LLM test results.", expected_keywords:"authentication, privacy, validation, metadata"},
    {...common, model:"demo-failing-v1", prompt:"Explain secure model evaluation and reliable result storage.", expected_keywords:"security, evaluation, storage", minimum_length:180, minimum_sentences:4}
  ];
  try {
    let lastResult;
    for (let index = 0; index < cases.length; index += 1) {
      suiteButton.firstElementChild.textContent = `Running case ${index + 1} of 3…`;
      lastResult = await executeTest(cases[index]);
    }
    showResult(lastResult); await loadHistory();
  } catch (error) { errorBox.textContent = error.message; }
  finally { suiteButton.disabled = false; runButton.disabled = false; suiteButton.firstElementChild.textContent = "Run 3 case suite"; }
});

loadHistory().catch(() => {});
