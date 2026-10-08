const form = document.querySelector("#test-form");
const runButton = document.querySelector("#run-button");
const suiteButton = document.querySelector("#suite-button");
const errorBox = document.querySelector("#error");
const temp = document.querySelector("#temperature");
const totalBadge = document.querySelector("#score-total");
const history = [];

temp.addEventListener("input", () => {
  document.querySelector("#temp-value").textContent = temp.value;
});

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({
    "&":"&amp;",
    "<":"&lt;",
    ">":"&gt;",
    "'":"&#39;",
    '"':"&quot;"
  })[char]);
}

function parseTerms(value) {
  return String(value)
    .split(",")
    .map(item => item.trim())
    .filter(Boolean);
}

function clampWeight(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.min(100, Math.max(0, number));
}

function getWeights() {
  return {
    keyword: clampWeight(document.querySelector("#weight-keywords").value),
    relevance: clampWeight(document.querySelector("#weight-relevance").value),
    length: clampWeight(document.querySelector("#weight-length").value),
    sentences: clampWeight(document.querySelector("#weight-sentences").value),
    forbidden: clampWeight(document.querySelector("#weight-forbidden").value),
    valid: clampWeight(document.querySelector("#weight-valid").value)
  };
}

function totalWeights(weights = getWeights()) {
  return Object.values(weights).reduce((sum, value) => sum + value, 0);
}

function updateWeightState() {
  const total = totalWeights();
  const valid = total === 100;
  totalBadge.textContent = `${total} / 100`;
  totalBadge.classList.toggle("bad", !valid);
  runButton.disabled = !valid;
  suiteButton.disabled = !valid;
  errorBox.textContent = valid
    ? ""
    : "Scoring points must total 100 before you can run the test.";
}

document.querySelectorAll(".weight-input").forEach(input => {
  input.addEventListener("input", updateWeightState);
});

function generateResponse(prompt, model) {
  const words = prompt.match(/[A-Za-z0-9']+/g) || [];
  const topic = words.slice(0, 8).join(" ") || "the requested topic";

  if (model === "demo-partial-v1") {
    return `Partial response for: ${topic}. This answer provides a short overview but leaves out several requested details and supporting concepts.`;
  }

  if (model === "demo-failing-v1") {
    return "Error: the requested information is unavailable. The model could not complete the requested analysis.";
  }

  return `Complete analysis for: ${topic}. This response addresses the requested topic with structured reasoning and relevant technical details. Key concepts include testing, JSON, metadata, security, encryption, privacy, authentication, and reliable evaluation. It explains the execution pipeline, model invocation, response validation, and result storage clearly. The result is complete and ready for automated scoring.`;
}

function scoreResponse(payload, response) {
  const weights = payload.weights;
  const normalized = response.toLowerCase();
  const criteria = [];

  const keywordMatches = payload.expected_keywords.filter(term =>
    normalized.includes(term.toLowerCase())
  );
  const keywordRatio = payload.expected_keywords.length
    ? keywordMatches.length / payload.expected_keywords.length
    : 1;
  criteria.push({
    name: "Keyword coverage",
    passed: keywordRatio === 1,
    score: Math.round(keywordRatio * weights.keyword * 10) / 10,
    detail: payload.expected_keywords.length
      ? `Matched ${keywordMatches.length} of ${payload.expected_keywords.length} keywords`
      : "No required keywords configured"
  });

  const stopWords = new Set([
    "the","and","for","with","what","why","how","from","into","this","that",
    "explain","describe","write","provide","tell","are","is","to","of","in","on","a","an"
  ]);

  const promptTerms = new Set(
    (payload.prompt.toLowerCase().match(/[a-z0-9']+/g) || [])
      .filter(word => word.length > 2 && !stopWords.has(word))
  );
  const responseTerms = new Set(response.toLowerCase().match(/[a-z0-9']+/g) || []);
  const relevantMatches = [...promptTerms].filter(word => responseTerms.has(word)).length;
  const relevanceRatio = promptTerms.size ? relevantMatches / promptTerms.size : 1;

  criteria.push({
    name: "Prompt relevance",
    passed: relevanceRatio >= 0.5,
    score: Math.round(Math.min(1, relevanceRatio) * weights.relevance * 10) / 10,
    detail: `Matched ${relevantMatches} of ${promptTerms.size} meaningful prompt terms`
  });

  const lengthRatio = payload.minimum_length === 0
    ? 1
    : Math.min(1, response.length / payload.minimum_length);

  criteria.push({
    name: "Minimum length",
    passed: response.length >= payload.minimum_length,
    score: Math.round(lengthRatio * weights.length * 10) / 10,
    detail: `Response contains ${response.length} characters; target is ${payload.minimum_length}`
  });

  const sentences = response.split(/[.!?]+/).filter(part => part.trim()).length;
  const sentenceRatio = Math.min(1, sentences / Math.max(1, payload.minimum_sentences));

  criteria.push({
    name: "Sentence structure",
    passed: sentences >= payload.minimum_sentences,
    score: Math.round(sentenceRatio * weights.sentences * 10) / 10,
    detail: `Response contains ${sentences} sentences; target is ${payload.minimum_sentences}`
  });

  const foundForbidden = payload.forbidden_terms.filter(term =>
    normalized.includes(term.toLowerCase())
  );

  criteria.push({
    name: "Forbidden terms",
    passed: foundForbidden.length === 0,
    score: foundForbidden.length === 0 ? weights.forbidden : 0,
    detail: foundForbidden.length === 0
      ? "No forbidden terms detected"
      : `Detected: ${foundForbidden.join(", ")}`
  });

  const validResponse = response.trim().length > 0;

  criteria.push({
    name: "Valid response",
    passed: validResponse,
    score: validResponse ? weights.valid : 0,
    detail: validResponse ? "Model returned usable text" : "Response is empty"
  });

  const score = Math.min(
    100,
    Math.round(criteria.reduce((sum, item) => sum + item.score, 0) * 10) / 10
  );

  return {score, criteria};
}

function formPayload() {
  return {
    prompt: document.querySelector("#prompt").value.trim(),
    expected_keywords: parseTerms(document.querySelector("#keywords").value),
    model: document.querySelector("#model").value,
    temperature: Number(temp.value),
    minimum_length: Number(document.querySelector("#minimum-length").value),
    minimum_sentences: Number(document.querySelector("#minimum-sentences").value),
    forbidden_terms: parseTerms(document.querySelector("#forbidden-terms").value),
    weights: getWeights()
  };
}

function executeSimulation(payload) {
  const started = performance.now();
  const response = generateResponse(payload.prompt, payload.model);
  const scored = scoreResponse(payload, response);
  const latency = Math.max(1, Math.round(performance.now() - started) + 42);

  return {
    id: `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`,
    status: "completed",
    prompt: payload.prompt,
    model: payload.model,
    provider: "local_demo",
    response,
    score: scored.score,
    passed: scored.score >= 75,
    criteria: scored.criteria,
    latency_ms: latency,
    created_at: new Date().toISOString(),
    metadata: {
      temperature: payload.temperature,
      expected_keywords: payload.expected_keywords,
      minimum_length: payload.minimum_length,
      minimum_sentences: payload.minimum_sentences,
      forbidden_terms: payload.forbidden_terms,
      scoring_weights: payload.weights,
      schema_version: "frontend-preview"
    }
  };
}

function showResult(result) {
  document.querySelector("#empty-state").hidden = true;
  document.querySelector("#result").hidden = false;
  document.querySelector("#score").textContent = Math.round(result.score);

  const badge = document.querySelector("#badge");
  badge.textContent = result.passed ? "PASS" : "REVIEW";
  badge.className = `badge ${result.passed ? "" : "fail"}`;

  document.querySelector("#result-title").textContent =
    result.passed ? "Test passed" : "Needs review";
  document.querySelector("#metadata").textContent =
    `${result.model} · ${result.latency_ms} ms · ${result.provider}`;
  document.querySelector("#response").textContent = result.response;

  document.querySelector("#criteria").innerHTML = result.criteria.map(item => `
    <div class="criterion">
      <span class="mark ${item.passed ? "" : "fail"}">${item.passed ? "✓" : "×"}</span>
      <div>
        <strong>${escapeHtml(item.name)}</strong>
        <p>${escapeHtml(item.detail)}</p>
      </div>
      <span class="points">${item.score}</span>
    </div>
  `).join("");

  document.querySelector("#json-result").textContent =
    JSON.stringify(result, null, 2);
}

function renderHistory() {
  const container = document.querySelector("#history");

  if (!history.length) {
    container.innerHTML = '<p class="muted">No saved executions yet.</p>';
    return;
  }

  container.innerHTML = history.map(item => `
    <div class="history-row">
      <code>${escapeHtml(item.id.slice(0, 8))}</code>
      <span>${escapeHtml(item.prompt.slice(0, 70))}</span>
      <span class="provider">${escapeHtml(item.provider)}</span>
      <span class="history-score">${item.score}/100</span>
    </div>
  `).join("");
}

form.addEventListener("submit", event => {
  event.preventDefault();
  errorBox.textContent = "";

  if (totalWeights() !== 100) {
    updateWeightState();
    return;
  }

  runButton.disabled = true;
  runButton.firstElementChild.textContent = "Executing…";

  try {
    const result = executeSimulation(formPayload());
    history.unshift(result);
    if (history.length > 10) history.length = 10;
    showResult(result);
    renderHistory();
  } catch (error) {
    errorBox.textContent = error instanceof Error
      ? error.message
      : "The test could not be completed.";
  } finally {
    runButton.firstElementChild.textContent = "Run one test";
    updateWeightState();
  }
});

suiteButton.addEventListener("click", () => {
  errorBox.textContent = "";

  if (totalWeights() !== 100) {
    updateWeightState();
    return;
  }

  const common = {
    temperature: 0.2,
    minimum_length: 120,
    minimum_sentences: 3,
    forbidden_terms: ["error", "unavailable"],
    weights: getWeights()
  };

  const cases = [
    {
      ...common,
      model: "demo-strong-v1",
      prompt: "Explain how security and structured JSON improve an LLM testing pipeline.",
      expected_keywords: ["security", "JSON", "testing", "metadata"]
    },
    {
      ...common,
      model: "demo-partial-v1",
      prompt: "Describe authentication, privacy, and validation for stored LLM test results.",
      expected_keywords: ["authentication", "privacy", "validation", "metadata"]
    },
    {
      ...common,
      model: "demo-failing-v1",
      prompt: "Explain secure model evaluation and reliable result storage.",
      expected_keywords: ["security", "evaluation", "storage"],
      minimum_length: 180,
      minimum_sentences: 4
    }
  ];

  suiteButton.disabled = true;
  runButton.disabled = true;

  try {
    let lastResult;

    cases.forEach((payload, index) => {
      suiteButton.firstElementChild.textContent = `Running case ${index + 1} of 3…`;
      lastResult = executeSimulation(payload);
      history.unshift(lastResult);
    });

    if (history.length > 10) history.length = 10;
    showResult(lastResult);
    renderHistory();
  } finally {
    suiteButton.firstElementChild.textContent = "Run 3 case suite";
    updateWeightState();
  }
});

updateWeightState();
