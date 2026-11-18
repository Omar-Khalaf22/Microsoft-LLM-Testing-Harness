import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  defaultWeights,
  scoringLabels,
  runEvaluation,
  listCriteria,
  suggestCriteria,
  approveVersion,
  getVersion,
  saveDraft,
} from "./api";
import type {
  CriterionConfiguration,
  CriterionDefinition,
  DraftDefinition,
  Execution,
  SavedTestVersion,
  ScoringWeights,
  RunResponse,
  Recommendation,
} from "./api";
import CriteriaSuggestions, { criterionDraft, rowProblems } from "./CriteriaSuggestions";
import type { CriterionDraft } from "./CriteriaSuggestions";
import SavedExecution from "./SavedExecution";
import SavedTestPicker from "./SavedTestPicker";

const terms = (value: string) =>
  value
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
function selection(rows: CriterionDraft[]): CriterionConfiguration[] | null {
  const chosen = rows.filter((r) => r.included);
  if (!chosen.length || chosen.length > 100 || chosen.some((r) => Object.keys(rowProblems(r)).length))
    return null;
  const parsed = chosen.map((r) => ({
    criterion_id: r.criterion_id,
    ...(r.method ? { method: r.method } : {}),
    parameters: r.custom ? { ...r.custom } : JSON.parse(r.parametersText) as Record<string, unknown>,
    weight: Number(r.weightText),
  }));
  if (parsed.reduce((s, c) => s + Math.round(c.weight * 100), 0) !== 10000) return null;
  return parsed;
}
export default function RunForm({
  initialRun,
  initialVersion,
  onNewTest,
  onRunCreated,
  onOpenVersion,
  onReserved,
}: {
  initialRun: RunResponse | null;
  initialVersion: SavedTestVersion | null;
  onNewTest: () => void;
  onRunCreated: (run: RunResponse) => void;
  onOpenVersion: (version: SavedTestVersion) => void;
  onReserved: (execution: Execution) => void;
}) {
  const m = initialRun?.metadata;
  const d = initialVersion?.definition;
  const l = d?.legacy;
  const [saved, setSaved] = useState(initialVersion);
  const [dirty, setDirty] = useState(false);
  const [writing, setWriting] = useState(false);
  const [testName, setTestName] = useState(initialVersion?.name ?? m?.test_name ?? "");
  const [prompt, setPrompt] = useState(d?.prompt ?? initialRun?.prompt ?? "");
  const [objective, setObjective] = useState(d?.objective ?? m?.objective ?? "");
  const [model, setModel] = useState(m?.requested_model ?? "gpt-4.1-mini");
  const [temperature, setTemperature] = useState(m?.temperature ?? 0.2);
  const [base, setBase] = useState(d?.base_system_prompt ?? m?.base_system_prompt ?? "");
  const [custom, setCustom] = useState(d?.custom_system_prompt ?? m?.custom_system_prompt ?? "");
  const [legacy, setLegacy] = useState(d ? !!l : Boolean(initialRun && !m?.criteria));
  const [weights, setWeights] = useState<ScoringWeights>({
    ...defaultWeights,
    ...(l?.weights ?? m?.scoring_weights ?? {}),
  });
  const [keywords, setKeywords] = useState(
    (l?.expected_keywords ?? m?.expected_keywords ?? []).join(", "),
  );
  const [forbidden, setForbidden] = useState(
    (l?.forbidden_terms ?? m?.forbidden_terms ?? []).join(", "),
  );
  const [minLength, setMinLength] = useState(l?.minimum_length ?? m?.minimum_length ?? 80);
  const [sentences, setSentences] = useState(l?.minimum_sentences ?? m?.minimum_sentences ?? 3);
  const [rows, setRows] = useState<CriterionDraft[]>(
    (d?.criteria ?? m?.criteria ?? []).map(criterionDraft),
  );
  const [recommendation, setRecommendation] = useState<Recommendation | null>(
    m?.generated_configuration ?? null,
  );
  const [approved, setApproved] = useState(false);
  const [approvalNotice, setApprovalNotice] = useState("");
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
  const busy = generating || submitting || writing;
  const inline = !saved && !m?.execution_id && (legacy || !rows.some((row) => row.custom));
  const canSave = !!testName.trim() && !!prompt.trim() && (legacy ? legacyValid : !!parsed);
  // Any edit that changes what the user reviewed withdraws approval and says why, because
  // some of these fields (system instructions) sit in a collapsed section away from the box.
  function clearApproval(reason: string) {
    if (approved)
      setApprovalNotice(
        `Approval was cleared because ${reason}. Review the criteria and approve them again.`,
      );
    setApproved(false);
    setDirty(true);
  }
  function changeRows(
    next: CriterionDraft[],
    reason = "the criteria were edited",
  ) {
    setRows(next);
    clearApproval(reason);
  }
  function changedPrompt(value: string) {
    setPrompt(value);
    clearApproval("the test prompt changed");
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
      const manual = rows.filter((r) => !r.reason);
      changeRows([
        ...manual,
        ...result.suggestions.filter((s) => !manual.some((r) => r.criterion_id === s.criterion_id))
          .map((s) => ({
            ...criterionDraft({ criterion_id: s.criterion_id, parameters: s.parameters, weight: s.maximum_points }),
            reason: s.reason,
          })),
      ], "new suggestions were loaded");
    } catch (e) {
      if (!c.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Suggestions could not be generated",
        );
    } finally {
      if (!c.signal.aborted) setGenerating(false);
    }
  }
  async function write(approveDraft = false) {
    if (busy || !canSave || (approveDraft && (!saved || dirty || saved.state !== "draft"))) return;
    setWriting(true);
    setError("");
    const definition: DraftDefinition = {
      name: testName.trim(), objective, prompt, base_system_prompt: base, custom_system_prompt: custom,
      ...(legacy ? { legacy: {
        weights, expected_keywords: terms(keywords), forbidden_terms: terms(forbidden),
        minimum_length: minLength, minimum_sentences: sentences,
      } } : { criteria: parsed }),
    };
    const previous = saved ?? (m?.test_id && m.test_version
      ? { test_id: m.test_id, test_version: m.test_version } : undefined);
    try {
      setSaved(approveDraft ? await approveVersion(saved!) : await saveDraft(definition, previous));
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The version could not be saved.");
    } finally {
      setWriting(false);
    }
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      inFlight.current ||
      !inline ||
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
        <h2>Configure Test</h2>
        {(initialRun || saved) && (
          <button
            type="button"
            className="new-test-button"
            disabled={busy}
            onClick={onNewTest}
          >
            New Test
          </button>
        )}
      </div>
      <SavedTestPicker key={saved ? `${saved.test_id}/${saved.test_version}` : "library"}
        disabled={busy} onSelect={async (ref) => onOpenVersion(await getVersion(ref))} />
      {saved && <p role="status" className="muted">
        {saved.state === "approved" ? "Approved" : "Draft"} version {saved.test_version}
        {dirty ? " · Unsaved changes" : ""}
      </p>}
      {!saved && m?.test_id && (
        <p className="muted">
          Loaded version {m.test_version}. Changes to the prompt, system
          instructions, objective, or criteria create a new version. Earlier
          runs remain saved.
        </p>
      )}
      {initialRun && !saved && m?.base_system_prompt === undefined && (
        <p className="muted">
          This historical run has no saved system instructions. Configure
          instructions before creating a new run.
        </p>
      )}
      <fieldset className="form-fields" disabled={busy}>
        <label className="field">
          <span>Test Name</span>
          <input
            required
            maxLength={100}
            value={testName}
            onChange={(e) => { setTestName(e.target.value); if (saved) clearApproval("the test name changed"); }}
          />
        </label>
        <label className="field">
          <span>Testing Objective</span>
          <textarea
            rows={2}
            maxLength={2000}
            value={objective}
            onChange={(e) => {
              setObjective(e.target.value);
              clearApproval("the testing objective changed");
              setRecommendation(null);
            }}
            placeholder="What should a useful response accomplish?"
          />
        </label>
        <label className="field">
          <span>Test Prompt</span>
          <textarea
            rows={4}
            required
            maxLength={10000}
            value={prompt}
            onChange={(e) => changedPrompt(e.target.value)}
            placeholder="What should the model respond to?"
          />
        </label>
        {inline && <div className="field-row">
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
              <option value="gpt-5.4-mini" />
              <option value="gpt-5.4" />
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
        </div>}
        <details className="advanced-criteria">
          <summary>System Instructions</summary>
          <div className="advanced-criteria-controls">
            <label className="field">
              <span>
                Base System Instructions (blank uses the backend default)
              </span>
              <textarea
                rows={3}
                maxLength={10000}
                value={base}
                onChange={(e) => {
                  setBase(e.target.value);
                  clearApproval("the base system instructions changed");
                }}
              />
            </label>
            <label className="field">
              <span>Additional System Instructions</span>
              <textarea
                rows={3}
                maxLength={10000}
                value={custom}
                onChange={(e) => {
                  setCustom(e.target.value);
                  clearApproval("the additional system instructions changed");
                }}
              />
            </label>
          </div>
        </details>
      </fieldset>
      {!legacy ? (
        <>
          <section className="suggestion-controls">
            <h3>Recommend Criteria</h3>
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
              {generating ? "Generating Suggestions…" : "Generate Criteria"}
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
                Reload Criteria
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
          {inline && <label className="check-field approval">
            <input
              type="checkbox"
              checked={approved}
              disabled={busy || !parsed}
              onChange={(e) => {
                setApproved(e.target.checked);
                if (e.target.checked) setApprovalNotice("");
              }}
            />
            I reviewed and approve these criteria, parameters, and point
            allocations.
          </label>}
          {approvalNotice && !approved && (
            <p role="status" className="approval-notice">
              {approvalNotice}
            </p>
          )}
        </>
      ) : (
        <fieldset className="form-fields scoring-box" disabled={busy}>
          <legend>Original Six Automatic Checks (Legacy)</legend>
          <button type="button" className="secondary-button" onClick={() => {
            setLegacy(false);
            clearApproval("the scoring mode changed");
          }}>
            Switch to Criterion Picker
          </button>
          <div className="field-row">
            <label className="field">
              <span>Expected Keywords (comma separated)</span>
              <input
                value={keywords}
                onChange={(e) => { setKeywords(e.target.value); setDirty(true); }}
              />
            </label>
            <label className="field">
              <span>Forbidden Terms (comma separated)</span>
              <input
                value={forbidden}
                onChange={(e) => { setForbidden(e.target.value); setDirty(true); }}
              />
            </label>
            <label className="field">
              <span>Minimum Length</span>
              <input
                type="number"
                min={0}
                max={10000}
                value={minLength}
                onChange={(e) => { setMinLength(Number(e.target.value)); setDirty(true); }}
              />
            </label>
            <label className="field">
              <span>Minimum Sentences</span>
              <input
                type="number"
                min={1}
                max={20}
                value={sentences}
                onChange={(e) => { setSentences(Number(e.target.value)); setDirty(true); }}
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
                    onChange={(e) => {
                      setWeights((w) => ({
                        ...w,
                        [key]: Number(e.target.value),
                      }));
                      setDirty(true);
                    }}
                  />
                </label>
              ),
            )}
          </div>
          <p className="muted">
            A check set to 0 points is still evaluated and reported, but adds
            nothing to the total. Points must total 100.00.
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
      <div className="saved-actions">
        <button type="button" className="secondary-button" disabled={busy || !canSave || (!!saved && !dirty)}
          onClick={() => void write()}>Save Draft</button>
        {saved?.state === "draft" && <button type="button" className="primary-button"
          disabled={busy || dirty || !canSave} onClick={() => void write(true)}>
          Approve Version
        </button>}
        {inline && <button className="primary-button" type="submit"
          disabled={busy || (legacy ? !legacyValid : !parsed || !approved)}>
          {submitting ? "Running and Saving…" : "Run and Save Test"}
        </button>}
      </div>
      {saved?.state === "approved" && !dirty && (
        <SavedExecution key={saved.test_version} test={saved} onReserved={onReserved} />
      )}
    </form>
  );
}
