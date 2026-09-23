import { useState } from "react";
import type { FormEvent } from "react";

import { runEvaluation, type RunResponse } from "./api";

function parseTerms(value: string): string[] {
  return value
    .split(",")
    .map((term) => term.trim())
    .filter((term) => term.length > 0);
}

function RunForm({ onRunCreated }: { onRunCreated: (run: RunResponse) => void }) {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("gpt-4.1-mini");
  const [temperature, setTemperature] = useState(0.2);
  const [expectedKeywords, setExpectedKeywords] = useState("");
  const [forbiddenTerms, setForbiddenTerms] = useState("");
  const [minimumLength, setMinimumLength] = useState(0);
  const [minimumSentences, setMinimumSentences] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim()) {
      return;
    }

    setSubmitting(true);
    setErrorMessage("");
    try {
      const run = await runEvaluation({
        prompt,
        model,
        temperature,
        expected_keywords: parseTerms(expectedKeywords),
        forbidden_terms: parseTerms(forbiddenTerms),
        minimum_length: minimumLength,
        minimum_sentences: minimumSentences,
      });
      onRunCreated(run);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="run-form" onSubmit={handleSubmit}>
      <h2>Run Evaluation</h2>

      <label className="field">
        <span>Prompt</span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={4}
          required
        />
      </label>

      <div className="field-row">
        <label className="field">
          <span>Model</span>
          <input value={model} onChange={(event) => setModel(event.target.value)} />
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

      {errorMessage && <p className="error-text">{errorMessage}</p>}

      <button type="submit" disabled={submitting}>
        {submitting ? "Running…" : "Run Evaluation"}
      </button>
    </form>
  );
}

export default RunForm;
