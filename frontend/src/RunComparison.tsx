import { useEffect, useState } from "react";
import { getRun } from "./api";
import { capitalize } from "./titleCase";
import type { CriterionResult, RunResponse, RunSummary } from "./api";
import CriterionEvidence, { isJudged } from "./CriterionEvidence";

type Loaded = { run: RunResponse | null; loading: boolean; error: string };

function useRun(id: string): Loaded {
  const [state, setState] = useState<Loaded>({ run: null, loading: false, error: "" });
  useEffect(() => {
    if (!id) {
      setState({ run: null, loading: false, error: "" });
      return;
    }
    const controller = new AbortController();
    setState({ run: null, loading: true, error: "" });
    getRun(id, controller.signal)
      .then((run) => setState({ run, loading: false, error: "" }))
      .catch((e) => {
        if (controller.signal.aborted) return;
        setState({
          run: null,
          loading: false,
          error: e instanceof Error ? e.message : "The run could not be loaded",
        });
      });
    return () => controller.abort();
  }, [id]);
  return state;
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const known = (x: unknown): number | undefined =>
  typeof x === "number" && Number.isFinite(x) && x >= 0 ? x : undefined;

function tokens(run: RunResponse) {
  const input = known(run.metadata.usage?.input_tokens);
  const output = known(run.metadata.usage?.output_tokens);
  const total =
    known(run.metadata.usage?.total_tokens) ??
    (input !== undefined && output !== undefined ? input + output : undefined);
  return { input, output, total };
}

const showText = (value: unknown, missing = "Not saved") =>
  value === undefined || value === null || value === "" ? missing : String(value);

// What the run was scored against: the approved criteria, or the original six checks.
function rubricOf(run: RunResponse): unknown {
  const m = run.metadata;
  if (m.criteria)
    return m.criteria;
  return {
    legacy_check_points: m.scoring_weights ?? null,
    expected_keywords: m.expected_keywords ?? [],
    forbidden_terms: m.forbidden_terms ?? [],
    minimum_length: m.minimum_length ?? null,
    minimum_sentences: m.minimum_sentences ?? null,
  };
}

interface FieldRow {
  label: string;
  values: string[];
  changed: boolean;
  long?: boolean;
}

// One row per input, with one text value per compared run (A, B and optionally C).
function fieldRows(runs: RunResponse[]): FieldRow[] {
  const rows: FieldRow[] = [];
  const add = (
    label: string,
    pick: (run: RunResponse) => unknown,
    options: { long?: boolean; missing?: string } = {},
  ) => {
    const raw = runs.map(pick);
    rows.push({
      label,
      values: raw.map((value) => showText(value, options.missing)),
      changed: !raw.every((value) => same(value, raw[0])),
      long: options.long,
    });
  };
  add("Test Prompt", (r) => r.prompt, { long: true });
  add("Testing Objective", (r) => r.metadata.objective, { long: true });
  add("Base System Instructions", (r) => r.metadata.base_system_prompt, { long: true });
  add("Additional System Instructions", (r) => r.metadata.custom_system_prompt, { long: true });
  const rubrics = runs.map((r) => JSON.stringify(rubricOf(r), null, 2));
  rows.push({
    label: "Scoring Rubric",
    values: rubrics,
    changed: !rubrics.every((value) => value === rubrics[0]),
    long: true,
  });
  add("Requested Model", (r) => r.metadata.requested_model);
  add("Temperature", (r) => r.metadata.temperature);
  add("Test Version", (r) => r.metadata.test_version, { missing: "Unknown" });
  return rows;
}

function key(run: RunResponse, c: CriterionResult) {
  const config = run.metadata.criteria?.find((item) => item.criterion_id === c.criterion_id);
  const id = c.criterion_id ?? c.name;
  return config?.method || id.startsWith("custom_")
    ? `custom/${run.metadata.test_id ?? run.id}/${id}` : `catalog/${id}`;
}

function savedRow(run: RunResponse, c: CriterionResult) {
  const config = run.metadata.criteria?.find((item) => item.criterion_id === c.criterion_id);
  if (!config) return run.metadata.scoring_weights ? rubricOf(run) : null;
  const definition = run.metadata.criterion_definitions?.find((item) => item.id === c.criterion_id);
  return {
    config,
    revision: config.method ?? run.metadata.catalog_revision,
    definition,
    judge: isJudged(run, c) ? [run.metadata.judge_profile_id, run.metadata.judge_profile_revision] : undefined,
  };
}

const points = (c: CriterionResult | undefined) =>
  !c
    ? "Not evaluated"
    : c.score === null
      ? `Unavailable${c.maximum_points == null ? "" : ` / ${c.maximum_points.toFixed(2)}`}`
      : `${c.score.toFixed(2)}${
          c.maximum_points !== null && c.maximum_points !== undefined
            ? ` / ${c.maximum_points.toFixed(2)}`
            : ""
        }`;
const diff = (x: number | null | undefined, y: number | null | undefined, digits = 2) =>
  typeof x === "number" && typeof y === "number" && Number.isFinite(x) && Number.isFinite(y)
    ? `${y - x > 0 ? "+" : ""}${(y - x).toFixed(digits)}`
    : "—";
const total = (run: RunResponse) => (run.score === null ? "Unavailable" : run.score.toFixed(2) + " / 100.00");
const when = (run: RunSummary) => new Date(run.created_at).toLocaleString();
const optionLabel = (run: RunSummary) =>
  `${run.metadata.test_name || "Untitled test"} · version ${run.metadata.test_version ?? "unknown"} · ${when(run)} · ${run.model}`;


function Changed({ changed }: { changed: boolean }) {
  return changed ? <span className="changed-badge">Changed</span> : <span className="same-text">Same</span>;
}

const NAMES = ["Run A", "Run B", "Run C"];

// With three runs where two match, the index of the one that differs; otherwise null
// (all the same, or all different, in which case the whole row is highlighted instead).
function oddOneOut(values: string[]): number | null {
  if (values.length !== 3) return null;
  const [a, b, c] = values;
  if (a === b && b !== c) return 2;
  if (a === c && a !== b) return 1;
  if (b === c && a !== b) return 0;
  return null;
}

export default function RunComparison({
  runs,
  seedId,
  onBack,
}: {
  runs: RunSummary[];
  seedId?: string;
  onBack: () => void;
}) {
  const initialA = seedId && runs.some((r) => r.id === seedId) ? seedId : (runs[0]?.id ?? "");
  const [aId, setAId] = useState(initialA);
  const [bId, setBId] = useState(() => runs.find((r) => r.id !== initialA)?.id ?? "");
  const [cId, setCId] = useState("");
  const [three, setThree] = useState(false);
  const A = useRun(aId);
  const B = useRun(bId);
  const C = useRun(three ? cId : "");

  const ids = three ? [aId, bId, cId] : [aId, bId];
  const slots = three ? [A, B, C] : [A, B];
  const distinct = new Set(ids).size === ids.length;
  const ready = ids.every(Boolean) && slots.every((slot) => slot.run) && distinct;
  const loaded: RunResponse[] = ready ? slots.map((slot) => slot.run!) : [];
  const [first] = loaded;
  const rows = ready ? fieldRows(loaded) : [];
  const changedLabels = rows.filter((r) => r.changed).map((r) => r.label);
  const anyChanged = changedLabels.length > 0;

  function toggleThree() {
    if (three) {
      setThree(false);
      return;
    }
    setCId((current) => current || (runs.find((r) => r.id !== aId && r.id !== bId)?.id ?? ""));
    setThree(true);
  }

  const criteriaKeys: string[] = [];
  if (ready) {
    criteriaKeys.push(...new Set(loaded.flatMap((run) => run.criteria.map((c) => key(run, c)))));
  }
  const find = (run: RunResponse, k: string) => run.criteria.find((c) => key(run, c) === k);
  // A criterion is comparable when every run saved it with the same rubric as Run A.
  const comparable = (cells: (CriterionResult | undefined)[]) => {
    if (cells.some((cell) => !cell)) return false;
    const left = savedRow(first, cells[0]!);
    return left !== null && cells.slice(1).every((cell, i) => same(left, savedRow(loaded[i + 1], cell!)));
  };
  const comparableTotal = ready && criteriaKeys.length > 0 &&
    loaded.every((run) => same(rubricOf(first), rubricOf(run))) &&
    criteriaKeys.every((k) => comparable(loaded.map((run) => find(run, k))));
  const sameScore = ready && loaded.every((run) => run.score === first.score);
  const sameResponse = ready && loaded.every((run) => run.response === first.response);
  const tokenParts = loaded.map(tokens);
  const totalValues = loaded.map(total);
  const totalOdd = three && ready ? oddOneOut(loaded.map(total)) : null;

  const select = (id: string, label: string, value: string, set: (v: string) => void) => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => set(e.target.value)}>
        <option value="">Choose a Saved Run</option>
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {optionLabel(r)}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <section className={`panel comparison${three ? " three-runs" : ""}`} aria-labelledby="comparison-title">
      <div className="result-heading">
        <div className="comparison-title-row">
          <h2 id="comparison-title">{three ? "Compare Three Runs" : "Compare Two Runs"}</h2>
          <button
            type="button"
            className="icon-button add-run-button"
            aria-pressed={three}
            aria-label={three ? "Remove Run C and compare two runs" : "Add Run C and compare three runs"}
            title={three ? "Remove Run C" : "Add a third run (Run C)"}
            disabled={runs.length < 3 && !three}
            onClick={toggleThree}
          >
            <span aria-hidden="true">{three ? "−" : "+"}</span>
          </button>
        </div>
        <button type="button" className="secondary-button" onClick={onBack}>
          Close Comparison
        </button>
      </div>

      {runs.length < 2 ? (
        <p className="muted">Save at least two runs to compare them.</p>
      ) : (
        <>
          <div className={`field-row${three ? " three" : ""}`}>
            {select("compare-a", "Run A", aId, setAId)}
            {select("compare-b", "Run B", bId, setBId)}
            {three && select("compare-c", "Run C", cId, setCId)}
          </div>
          <div className="swap-row">
            <button
              type="button"
              className="text-button"
              onClick={() => {
                setAId(bId);
                setBId(aId);
              }}
            >
              Swap A and B
            </button>
            {three && (
              <>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    setBId(cId);
                    setCId(bId);
                  }}
                >
                  Swap B and C
                </button>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    setAId(cId);
                    setCId(aId);
                  }}
                >
                  Swap A and C
                </button>
              </>
            )}
          </div>

          {slots.some((slot) => slot.loading) && <p role="status">Loading runs…</p>}
          {slots.map((slot, i) =>
            slot.error ? (
              <p key={NAMES[i]} role="alert" className="error-text">
                {NAMES[i]}: {slot.error}
              </p>
            ) : null,
          )}
          {ids.every(Boolean) && !distinct && (
            <p role="status" className="muted">
              {three ? "Choose three different runs to see what changed." : "Choose two different runs to see what changed."}
            </p>
          )}
          {!ids.every(Boolean) && (
            <p className="muted">{three ? "Choose a run for A, B and C." : "Choose a run for both A and B."}</p>
          )}

          {ready && (
            <>
              <p role="status" className="change-summary">
                {anyChanged
                  ? `Changed between these runs: ${changedLabels.join(", ")}.`
                  : "The prompts, system instructions, rubric and settings are identical."}
              </p>

              <table className="compare-table">
                <caption>
                  Inputs, Rubric and Settings
                  {anyChanged && <span className="changed-tag">CHANGED</span>}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    {loaded.map((_, i) => (
                      <th key={NAMES[i]} scope="col">{NAMES[i]}</th>
                    ))}
                    {!three && <th scope="col">Difference</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const odd = three ? oddOneOut(r.values) : null;
                    return (
                    <tr key={r.label} data-changed={r.changed && odd === null}>
                      <th scope="row" data-field-changed={r.changed ? "true" : undefined}>{r.label}</th>
                      {r.values.map((value, i) => (
                        <td key={NAMES[i]} data-odd={odd === i ? "true" : undefined}>
                          {r.long ? <pre className="compare-text">{value}</pre> : value}
                        </td>
                      ))}
                      {!three && (
                        <td>
                          <Changed changed={r.changed} />
                        </td>
                      )}
                    </tr>
                    );
                  })}
                </tbody>
              </table>

              <table className="compare-table">
                <caption>Criterion Points</caption>
                <thead>
                  <tr>
                    <th scope="col">Criterion</th>
                    {three ? (
                      loaded.map((_, i) => <th key={NAMES[i]} scope="col">{NAMES[i]}</th>)
                    ) : (
                      <>
                        <th scope="col">Run A</th>
                        <th scope="col">Run B</th>
                        <th scope="col">B − A</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {criteriaKeys.map((k) => {
                    const cells = loaded.map((run) => find(run, k));
                    const matched = comparable(cells);
                    const changed = cells.every(Boolean) && !matched;
                    const [ca, cb] = cells;
                    const named = cells.find(Boolean)!;
                    const renamed = cells.every(Boolean) && cells.some((cell) => cell!.name !== cells[0]!.name);
                                      const odd = three ? oddOneOut(cells.map(points)) : null;
                    const rowChanged = changed || !cells.every((cell) => points(cell) === points(cells[0]));
                    return (
                      <tr key={k} data-changed={rowChanged && odd === null}>
                        <th scope="row" data-field-changed={rowChanged ? "true" : undefined}>{named.name}</th>
                        {cells.map((cell, i) => (
                          <td key={NAMES[i]} data-odd={odd === i ? "true" : undefined}>
                            {renamed && cell && <strong>{cell.name}</strong>}
                            <div>{points(cell)}</div>
                            {cell && <CriterionEvidence row={cell} run={loaded[i]} />}
                          </td>
                        ))}
                        {!three && (
                          <td>{changed
                            ? <span className="changed-badge">Rubric differs or is unavailable</span>
                            : matched ? diff(ca?.score, cb?.score) : "—"}</td>
                        )}
                      </tr>
                    );
                  })}
                  <tr className="total-row" data-changed={!sameScore && totalOdd === null}>
                    <th scope="row" data-field-changed={!sameScore ? "true" : undefined}>Automated Total</th>
                    {loaded.map((run, i) => (
                      <td key={NAMES[i]} data-odd={totalOdd === i ? "true" : undefined}>{total(run)}</td>
                    ))}
                    {!three && <td>{comparableTotal ? diff(loaded[0].score, loaded[1].score) : "—"}</td>}
                  </tr>
                </tbody>
              </table>
              {loaded.some((run) => run.score === null) && (
                <p className="muted">
                  A total is unavailable when any selected criterion has no valid result.
                </p>
              )}

              <table className="compare-table">
                <caption>Execution</caption>
                <thead>
                  <tr>
                    <th scope="col">Measure</th>
                    {loaded.map((_, i) => (
                      <th key={NAMES[i]} scope="col">{NAMES[i]}</th>
                    ))}
                    {!three && <th scope="col">B − A</th>}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Status</th>
                    {loaded.map((run, i) => <td key={NAMES[i]}>{capitalize(run.status)}</td>)}
                    {!three && <td>—</td>}
                  </tr>
                  <tr>
                    <th scope="row">Model Used</th>
                    {loaded.map((run, i) => <td key={NAMES[i]}>{run.model}</td>)}
                    {!three && <td>—</td>}
                  </tr>
                  <tr>
                    <th scope="row">Latency</th>
                    {loaded.map((run, i) => (
                      <td key={NAMES[i]}>
                        {run.latency_ms === null ? "Unavailable" : `${run.latency_ms} ms`}
                      </td>
                    ))}
                    {!three && <td>{diff(loaded[0].latency_ms, loaded[1].latency_ms, 0)} ms</td>}
                  </tr>
                  {(["input", "output", "total"] as const).map((part) => (
                    <tr key={part}>
                      <th scope="row">{part[0].toUpperCase() + part.slice(1)} Tokens</th>
                      {tokenParts.map((t, i) => (
                        <td key={NAMES[i]}>
                          {t[part] ?? "Not reported"}
                        </td>
                      ))}
                      {!three && <td>{diff(tokenParts[0][part], tokenParts[1][part], 0)}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>

              <h3>Responses</h3>
              <p className="muted">
                {sameResponse
                  ? three ? "The three responses are identical." : "The two responses are identical."
                  : "The responses differ."}
              </p>
              <div className={`field-row${three ? " three" : ""}`}>
                {loaded.map((run, i) => (
                  <div className="response-box" key={NAMES[i]}>
                    <h4>{NAMES[i]}</h4>
                    <p>{run.response || "No response was saved."}</p>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
