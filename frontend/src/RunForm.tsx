import { useState } from "react";
import type { FormEvent } from "react";

import { apiBaseUrl, runEvaluation, type RunResponse } from "./api";

function parseTerms(value: string): string[] {
  return value
    .split(",")
    .map((term) => term.trim())
    .filter((term) => term.length > 0);
}

function RunForm({
  initialRun,
  onNewTest,
  onRunCreated,
}: {
  initialRun: RunResponse | null;
  onNewTest: () => void;
  onRunCreated: (run: RunResponse) => void;
}) {
  const testId = initialRun?.metadata.test_id;
  const [testName, setTestName] = useState(initialRun?.metadata.test_name ?? "");
  const [prompt, setPrompt] = useState(initialRun?.prompt ?? "");
  const [model, setModel] = useState(initialRun?.metadata.requested_model ?? "gpt-4.1-mini");
  const [temperature, setTemperature] = useState(initialRun?.metadata.temperature ?? 0.2);
  const [expectedKeywords, setExpectedKeywords] = useState(
    initialRun?.metadata.expected_keywords.join(", ") ?? "",
  );
  const [forbiddenTerms, setForbiddenTerms] = useState(
    initialRun?.metadata.forbidden_terms.join(", ") ?? "",
  );
  const [minimumLength, setMinimumLength] = useState(initialRun?.metadata.minimum_length ?? 0);
  const [minimumSentences, setMinimumSentences] = useState(
    initialRun?.metadata.minimum_sentences ?? 1,
  );
  const [weights, setWeights] = useState<Record<string, number>>(
    initialRun?.metadata.scoring_weights ?? {
      keywords: 30, relevance: 20, length: 15,
      sentences: 15, forbidden: 10, nonempty: 10,
    },
  );
  const weightTotal = Object.values(weights).reduce((sum, value) => sum + value, 0);
  const validWeights = weightTotal === 100 && Object.values(weights).every(
    (value) => Number.isInteger(value) && value >= 0,
  );
  const [suggesting, setSuggesting] = useState(false);
  const [suggested, setSuggested] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  async function suggestCriteria() {
    setSuggesting(true);
    setErrorMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}/runs/suggest-criteria`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      if (!response.ok) throw new Error("GPT-4o mini suggestions are unavailable");
      const data = (await response.json()) as { criteria: string[] };
      setSuggested(data.criteria);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Suggestion failed");
    } finally {
      setSuggesting(false);
    }
  }
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim() || !testName.trim() || !validWeights) {
      return;
    }

    setSubmitting(true);
    setErrorMessage("");
    try {
      const run = await runEvaluation({
        test_name: testName.trim(),
        prompt,
        model,
        temperature,
        expected_keywords: parseTerms(expectedKeywords),
        scoring_weights: weights,
        forbidden_terms: parseTerms(forbiddenTerms),
        minimum_length: minimumLength,
        minimum_sentences: minimumSentences,
        ...(testId ? { test_id: testId } : {}),
        ...(testId && initialRun?.metadata.test_version
          ? { test_version: initialRun.metadata.test_version }
          : {}),
      });
      onRunCreated(run);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="panel run-form" onSubmit={handleSubmit}>
      <div className="run-form-heading">
        <div className="section-title">
          <span className="section-number">01</span>
          <h2>Configure test</h2>
        </div>
        {initialRun && (
          <button type="button" className="new-test-button" onClick={onNewTest}>
            New test
          </button>
        )}
      </div>
      {testId && (
        <p className="muted test-version-note">
          Loaded version {initialRun?.metadata.test_version ?? 1}. Changing the name, prompt, or
          scoring rules saves a new version. Model and temperature changes create another run.
        </p>
      )}
      {initialRun && !testId && (
        <p className="muted test-version-note">Imported result loaded. Submitting will save a new test.</p>
      )}

      <label className="field">
        <span>Test name <span className="required-mark" aria-hidden="true">*</span></span>
        <input
          value={testName}
          onChange={(event) => setTestName(event.target.value)}
          placeholder="e.g. JSON response check"
          maxLength={100}
          required
        />
      </label>

      <label className="field">
        <span>Test prompt <span className="required-mark" aria-hidden="true">*</span></span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={4}
          maxLength={10000}
          placeholder="What should the model respond to?"
          required
        />
      </label>

      <div className="field-row">
        <label className="field">
          <span>Model</span>
          <input value={model} onChange={(event) => setModel(event.target.value)} list="model-options" />
          <datalist id="model-options">
            <option value="demo-strong-v1" />
            <option value="demo-partial-v1" />
            <option value="demo-failing-v1" />
          </datalist>
        </label>

        <label className="field">
          <span>Temperature</span>
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            onChange={(event) => setTemperature(Number(event.target.value))}
          />
        </label>
      </div>

      <div className="field-row">
        <label className="field">
          <span>Expected keywords (comma separated)</span>
          <input
            value={expectedKeywords}
            onChange={(event) => setExpectedKeywords(event.target.value)}
          />
        </label>

        <label className="field">
          <span>Forbidden terms (comma separated)</span>
          <input
            value={forbiddenTerms}
            onChange={(event) => setForbiddenTerms(event.target.value)}
          />
        </label>
      </div>

      <div className="field-row">
        <label className="field">
          <span>Minimum length</span>
          <input
            type="number"
            min={0}
            max={10000}
            value={minimumLength}
            onChange={(event) => setMinimumLength(Number(event.target.value))}
          />
        </label>

        <label className="field">
          <span>Minimum sentences</span>
          <input
            type="number"
            min={1}
            max={20}
            value={minimumSentences}
            onChange={(event) => setMinimumSentences(Number(event.target.value))}
          />
        </label>
      </div>

      <div className="field">
        <button type="button" disabled={suggesting || !prompt.trim()}
          onClick={suggestCriteria}>
          {suggesting ? "Suggesting…" : "Suggest criteria with GPT-4o mini"}
        </button>
        {suggested.length > 0 && <p className="muted">
          Suggested: {suggested.join(", ")}. Review and adjust the points below.
        </p>}
        <span>Scoring points (total: {weightTotal}/100)</span>
        <div className="field-row">
          {Object.entries(weights).map(([key, value]) => (
            <label className="field" key={key}>
              <span>{key}</span>
              <input type="number" min={0} max={100} step={1} value={value}
                onChange={(event) => setWeights((previous) => ({
                  ...previous, [key]: Number(event.target.value),
                }))} />
            </label>
          ))}
        </div>
        {!validWeights && <p className="error-text">Points must total exactly 100.</p>}
      </div>
      {errorMessage && <p className="error-text" role="alert">{errorMessage}</p>}

      <button type="submit" className="primary-button" disabled={submitting || !validWeights}>
        <span>{submitting ? "Running…" : "Run and save test"}</span>
        <span aria-hidden="true">→</span>
      </button>
    </form>
  );
}

export default RunForm;
