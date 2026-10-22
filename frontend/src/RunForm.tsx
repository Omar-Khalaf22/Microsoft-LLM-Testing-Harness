import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  defaultWeights,
  scoringLabels,
  runEvaluation,
  listCriteria,
  suggestCriteria,
} from "./api";
import type {
  CriterionConfiguration,
  CriterionDefinition,
  ScoringWeights,
  RunResponse,
  Recommendation,
} from "./api";
import CriteriaSuggestions from "./CriteriaSuggestions";
import type { CriterionDraft } from "./CriteriaSuggestions";

const terms = (value: string) =>
  value
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
const centsValid = (value: number) =>
  Number.isFinite(value) &&
  value > 0 &&
  value <= 100 &&
  Math.abs(value * 100 - Math.round(value * 100)) < 1e-8;
function selection(rows: CriterionDraft[]): CriterionConfiguration[] | null {
  try {
    const chosen = rows.filter((r) => r.included);
    if (!chosen.length) return null;
    const parsed = chosen.map((r) => ({
      criterion_id: r.criterion_id,
      parameters: JSON.parse(r.parametersText) as Record<string, unknown>,
      weight: Number(r.weightText),
    }));
    if (
      parsed.some(
        (c) =>
          !centsValid(c.weight) ||
          !c.parameters ||
          Array.isArray(c.parameters) ||
          typeof c.parameters !== "object",
      )
    )
      return null;
    if (parsed.reduce((s, c) => s + Math.round(c.weight * 100), 0) !== 10000)
      return null;
    return parsed;
  } catch {
    return null;
  }
}
export default function RunForm({
  initialRun,
  onNewTest,
  onRunCreated,
}: {
  initialRun: RunResponse | null;
  onNewTest: () => void;
  onRunCreated: (run: RunResponse) => void;
}) {
  const m = initialRun?.metadata;
  const [testName, setTestName] = useState(m?.test_name ?? "");
  const [prompt, setPrompt] = useState(initialRun?.prompt ?? "");
  const [objective, setObjective] = useState(m?.objective ?? "");
  const [model, setModel] = useState(m?.requested_model ?? "gpt-4.1-mini");
  const [temperature, setTemperature] = useState(m?.temperature ?? 0.2);
  const [base, setBase] = useState(m?.base_system_prompt ?? "");
  const [custom, setCustom] = useState(m?.custom_system_prompt ?? "");
  const [legacy, setLegacy] = useState(Boolean(initialRun && !m?.criteria));
  const [weights, setWeights] = useState<ScoringWeights>({
    ...defaultWeights,
    ...(m?.scoring_weights ?? {}),
  });
  const [keywords, setKeywords] = useState(
    (m?.expected_keywords ?? []).join(", "),
  );
  const [forbidden, setForbidden] = useState(
    (m?.forbidden_terms ?? []).join(", "),
  );
  const [minLength, setMinLength] = useState(m?.minimum_length ?? 80);
  const [sentences, setSentences] = useState(m?.minimum_sentences ?? 3);
  const [rows, setRows] = useState<CriterionDraft[]>(
    (m?.criteria ?? []).map((c) => ({
      criterion_id: c.criterion_id,
      parametersText: JSON.stringify(c.parameters, null, 2),
      weightText: String(c.weight),
      included: true,
    })),
  );
  const [recommendation, setRecommendation] = useState<Recommendation | null>(
    m?.generated_configuration ?? null,
  );
  const [approved, setApproved] = useState(false);
  const [catalog, setCatalog] = useState<CriterionDefinition[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const generateController = useRef<AbortController | null>(null);
  const submitController = useRef<AbortController | null>(null);
  useEffect(() => {
    const c = new AbortController();
    listCriteria(c.signal)
      .then((r) => {
        setCatalog(r.criteria);
        setCatalogError("");
      })
      .catch((e) => {
        if (!c.signal.aborted)
          setCatalogError(
            e instanceof Error ? e.message : "Criteria could not be loaded",
          );
      });
    return () => c.abort();
  }, [catalogRetry]);
  useEffect(
    () => () => {
      generateController.current?.abort();
      submitController.current?.abort();
    },
    [],
  );
  const parsed = selection(rows);
  const total = rows
    .filter((r) => r.included)
    .reduce((s, r) => s + (Number(r.weightText) || 0), 0);
  const legacyValid =
    Object.values(weights).every(
      (v) =>
        Number.isFinite(v) &&
        v >= 0 &&
        v <= 100 &&
        Math.abs(v * 100 - Math.round(v * 100)) < 1e-8,
    ) &&
    Object.values(weights).reduce((s, v) => s + Math.round(v * 100), 0) ===
      10000;
  const busy = generating || submitting;
  function changeRows(next: CriterionDraft[]) {
    setRows(next);
    setApproved(false);
  }
  function changedPrompt(value: string) {
    setPrompt(value);
    setApproved(false);
    setRecommendation(null);
  }
  async function generate() {
    if (generating) return;
    const c = new AbortController();
    generateController.current = c;
    setGenerating(true);
    setError("");
    try {
      const result = await suggestCriteria(objective, prompt, c.signal);
      if (c.signal.aborted) return;
      setRecommendation(result);
      setLegacy(false);
      changeRows(
        result.suggestions.map((s) => ({
          criterion_id: s.criterion_id,
          parametersText: JSON.stringify(s.parameters, null, 2),
          weightText: String(s.maximum_points),
          reason: s.reason,
          included: true,
        })),
      );
    } catch (e) {
      if (!c.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Suggestions could not be generated",
        );
    } finally {
      if (!c.signal.aborted) setGenerating(false);
    }
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      inFlight.current ||
      busy ||
      !testName.trim() ||
      !prompt.trim() ||
      (legacy ? !legacyValid : !parsed || !approved)
    )
      return;
    inFlight.current = true;
    setSubmitting(true);
    setError("");
    const c = new AbortController();
    submitController.current = c;
    try {
      const result = await runEvaluation(
        {
          test_name: testName.trim(),
          prompt,
          objective,
          model,
          temperature,
          base_system_prompt: base,
          custom_system_prompt: custom,
          ...(legacy
            ? {
                weights,
                expected_keywords: terms(keywords),
                forbidden_terms: terms(forbidden),
                minimum_length: minLength,
                minimum_sentences: sentences,
              }
            : {
                criteria: parsed!,
                configuration_state: "approved" as const,
                ...(recommendation
                  ? { recommendation_id: recommendation.recommendation_id }
                  : {}),
              }),
          ...(m?.test_id
            ? { test_id: m.test_id, test_version: m.test_version }
            : {}),
        },
        c.signal,
      );
      if (!c.signal.aborted) onRunCreated(result);
    } catch (e) {
      if (!c.signal.aborted)
        setError(e instanceof Error ? e.message : "The run could not be saved");
    } finally {
      inFlight.current = false;
      if (!c.signal.aborted) setSubmitting(false);
    }
  }
  return (
    <form
      className="panel run-form"
      onSubmit={(e) => void submit(e)}
      aria-busy={busy}
    >
      <div className="run-form-heading">
        <h2>Configure test</h2>
        {initialRun && (
          <button
            type="button"
            className="new-test-button"
            disabled={busy}
            onClick={onNewTest}
          >
            New test
          </button>
        )}
      </div>
      {m?.test_id && (
        <p className="muted">
          Loaded version {m.test_version}. Changes to the prompt, system
          instructions, objective, or criteria create a new version. Earlier
          runs remain saved.
        </p>
      )}
      {initialRun && m?.base_system_prompt === undefined && (
        <p className="muted">
          This historical run has no saved system instructions. Configure
          instructions before creating a new run.
        </p>
      )}
      <fieldset className="form-fields" disabled={busy}>
        <label className="field">
          <span>Test name</span>
          <input
            required
            maxLength={100}
            value={testName}
            onChange={(e) => setTestName(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Testing objective</span>
          <textarea
            rows={2}
            maxLength={2000}
            value={objective}
            onChange={(e) => {
              setObjective(e.target.value);
              setApproved(false);
              setRecommendation(null);
            }}
            placeholder="What should a useful response accomplish?"
          />
        </label>
        <label className="field">
          <span>Test prompt</span>
          <textarea
            rows={4}
            required
            maxLength={10000}
            value={prompt}
            onChange={(e) => changedPrompt(e.target.value)}
            placeholder="What should the model respond to?"
          />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Model</span>
            <input
              required
              maxLength={200}
              list="models"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
            <datalist id="models">
              <option value="gpt-4.1-mini" />
              <option value="demo-json-v1" />
              <option value="demo-strong-v1" />
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
              onChange={(e) => setTemperature(Number(e.target.value))}
            />
          </label>
        </div>
        <details className="advanced-criteria">
          <summary>System instructions</summary>
          <div className="advanced-criteria-controls">
            <label className="field">
              <span>
                Base system instructions (blank uses the backend default)
              </span>
              <textarea
                rows={3}
                maxLength={10000}
                value={base}
                onChange={(e) => setBase(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Additional system instructions</span>
              <textarea
                rows={3}
                maxLength={10000}
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
              />
            </label>
          </div>
        </details>
        <label className="check-field">
          <input
            type="checkbox"
            checked={legacy}
            onChange={(e) => {
              setLegacy(e.target.checked);
              setApproved(false);
            }}
          />
          Use the original six-check configuration
        </label>
      </fieldset>
      {!legacy ? (
        <>
          <section className="suggestion-controls">
            <h3>Recommend criteria</h3>
            <p className="muted">
              Suggestions use your objective and prompt. Review them before
              running the test.
            </p>
            <button
              className="secondary-button"
              type="button"
              disabled={
                busy || !objective.trim() || !prompt.trim() || !catalog.length
              }
              onClick={() => void generate()}
            >
              {generating ? "Generating suggestions…" : "Generate criteria"}
            </button>
            {recommendation && (
              <p role="status">
                {recommendation.provider === "local_demo"
                  ? "Demo suggestions · no LLM request was made."
                  : `Suggested by ${recommendation.assistant_model}.`}{" "}
                Changes below become your approved configuration.
              </p>
            )}
          </section>
          {catalogError && (
            <p role="alert" className="error-text">
              {catalogError}{" "}
              <button
                type="button"
                onClick={() => setCatalogRetry((x) => x + 1)}
              >
                Reload criteria
              </button>
            </p>
          )}
          <CriteriaSuggestions
            catalog={catalog}
            rows={rows}
            onChange={changeRows}
            disabled={busy}
          />
          <output
            className={`score-total ${parsed ? "" : "bad"}`}
            aria-live="polite"
          >
            Allocated: {total.toFixed(2)} / 100.00
          </output>
          {!parsed && rows.length > 0 && (
            <p className="error-text">
              Include at least one criterion. Use valid parameter JSON and
              positive points with up to two decimals totaling 100.00.
            </p>
          )}
          <label className="check-field approval">
            <input
              type="checkbox"
              checked={approved}
              disabled={busy || !parsed}
              onChange={(e) => setApproved(e.target.checked)}
            />
            I reviewed and approve these criteria, parameters, and point
            allocations.
          </label>
        </>
      ) : (
        <fieldset className="form-fields scoring-box" disabled={busy}>
          <legend>Original six checks</legend>
          <div className="field-row">
            <label className="field">
              <span>Expected keywords (comma separated)</span>
              <input
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Forbidden terms (comma separated)</span>
              <input
                value={forbidden}
                onChange={(e) => setForbidden(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Minimum length</span>
              <input
                type="number"
                min={0}
                max={10000}
                value={minLength}
                onChange={(e) => setMinLength(Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>Minimum sentences</span>
              <input
                type="number"
                min={1}
                max={20}
                value={sentences}
                onChange={(e) => setSentences(Number(e.target.value))}
              />
            </label>
          </div>
          <div className="score-grid">
            {(Object.keys(scoringLabels) as (keyof ScoringWeights)[]).map(
              (key) => (
                <label className="score-item" key={key}>
                  <span>{scoringLabels[key]} points</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.01}
                    value={weights[key]}
                    onChange={(e) =>
                      setWeights((w) => ({
                        ...w,
                        [key]: Number(e.target.value),
                      }))
                    }
                  />
                </label>
              ),
            )}
          </div>
          <p className="muted">
            Zero disables a legacy check. Total must equal 100.00.
          </p>
          {!legacyValid && (
            <p className="error-text">Check the point allocations and total.</p>
          )}
        </fieldset>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      <button
        className="primary-button"
        type="submit"
        disabled={busy || (legacy ? !legacyValid : !parsed || !approved)}
      >
        {submitting ? "Running and saving…" : "Run and save test"}
      </button>
    </form>
  );
}
