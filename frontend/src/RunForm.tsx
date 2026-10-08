import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { defaultWeights, scoringLabels, runEvaluation, type ScoringWeights, type RunResponse } from "./api";

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
  const inFlight = useRef(false);
  const [weights, setWeights] = useState<ScoringWeights>({ ...defaultWeights, ...initialRun?.metadata.scoring_weights });
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);
  const weightsValid = Object.values(weights).every(value => Number.isFinite(value) && value >= 0 && value <= 100) && Math.abs(total - 100) < 1e-8;
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
  const [minimumLength, setMinimumLength] = useState(initialRun?.metadata.minimum_length ?? 80);
  const [minimumSentences, setMinimumSentences] = useState(
    initialRun?.metadata.minimum_sentences ?? 3,
  );
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !weightsValid || !prompt.trim() || !testName.trim()) {
      return;
    }

    inFlight.current = true;
    setSubmitting(true);
    setErrorMessage("");
    try {
      const run = await runEvaluation({
        weights,
        test_name: testName.trim(),
        prompt,
        model,
        temperature,
        expected_keywords: parseTerms(expectedKeywords),
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
      inFlight.current = false;
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
        <span className="prompt-box">
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={4}
            maxLength={500}
            placeholder="What should the model respond to?"
            required
          />
          <span className="prompt-counter" aria-hidden="true">{prompt.length} / 500</span>
        </span>
      </label>

      <div className="field-row">
        <label className="field">
          <span>Model</span>
          <input value={model} onChange={(event) => setModel(event.target.value)} list="model-options" />
          <datalist id="model-options">
            <option value="gpt-4.1-mini" />
          </datalist>
        </label>

        <label className="field">
          <span>Temperature <output>{temperature.toFixed(1)}</output></span>
          <input
            type="range"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            onChange={(event) => setTemperature(Number(event.target.value))}
          />
        </label>
      </div>

      <details className="advanced-criteria">
        <summary className="advanced-criteria-header">
          <span>
            <strong>Evaluation Criteria &amp; Scoring</strong>
            <span className="advanced-criteria-description">Configure response constraints and scoring weights.</span>
          </span>
          <svg className="criteria-chevron" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </summary>
        <div className="advanced-criteria-controls">
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

          <section className="scoring-box" aria-labelledby="scoring-title">
            <div className="scoring-head"><div><h3 id="scoring-title">Scoring points</h3><p>Choose how the 100 points are divided for this run.</p></div><output className={`score-total ${weightsValid ? "" : "bad"}`}>{Number(total.toFixed(1))} / 100</output></div>
            <div className="score-grid">{(Object.keys(scoringLabels) as (keyof ScoringWeights)[]).map(key => <label className="score-item" key={key}><span>{scoringLabels[key]}</span><input aria-label={`${scoringLabels[key]} weight`} type="number" min={0} max={100} step={0.1} value={weights[key]} onChange={event => setWeights(previous => ({...previous, [key]: Number(event.target.value)}))} /></label>)}</div>
            <p className="score-note">Set a criterion to 0 if you do not want it counted. Total must equal 100.</p>
            {!weightsValid && <p className="error-text" role="alert">Scoring points must total 100 before you can run the test.</p>}
          </section>
        </div>
      </details>
      {errorMessage && <p className="error-text" role="alert">{errorMessage}</p>}

      <button type="submit" className="primary-button" disabled={submitting || !weightsValid}>
        <span>{submitting ? "Running…" : "Run and save test"}</span>
        <span aria-hidden="true">→</span>
      </button>
    </form>
  );
}

export default RunForm;
