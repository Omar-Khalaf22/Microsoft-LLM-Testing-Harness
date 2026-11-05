import { useEffect, useState } from "react";
import { getRun } from "./api";
import type { CriterionResult, RunResponse, RunSummary } from "./api";

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
    return [...m.criteria]
      .map((c) => ({ id: c.criterion_id, points: c.weight, parameters: c.parameters }))
      .sort((a, b) => a.id.localeCompare(b.id));
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
  a: string;
  b: string;
  changed: boolean;
  long?: boolean;
}

function fieldRows(a: RunResponse, b: RunResponse): FieldRow[] {
  const rows: FieldRow[] = [];
  const add = (
    label: string,
    va: unknown,
    vb: unknown,
    options: { long?: boolean; missing?: string } = {},
  ) =>
    rows.push({
      label,
      a: showText(va, options.missing),
      b: showText(vb, options.missing),
      changed: !same(va, vb),
      long: options.long,
    });
  add("Test prompt", a.prompt, b.prompt, { long: true });
  add("Testing objective", a.metadata.objective, b.metadata.objective, { long: true });
  add("Base system instructions", a.metadata.base_system_prompt, b.metadata.base_system_prompt, {
    long: true,
  });
  add(
    "Additional system instructions",
    a.metadata.custom_system_prompt,
    b.metadata.custom_system_prompt,
    { long: true },
  );
  const ra = JSON.stringify(rubricOf(a), null, 2);
  const rb = JSON.stringify(rubricOf(b), null, 2);
  rows.push({ label: "Scoring rubric", a: ra, b: rb, changed: ra !== rb, long: true });
  add("Requested model", a.metadata.requested_model, b.metadata.requested_model);
  add("Temperature", a.metadata.temperature, b.metadata.temperature);
  add("Test version", a.metadata.test_version, b.metadata.test_version, { missing: "Unknown" });
  return rows;
}

const key = (c: CriterionResult) => c.criterion_id ?? c.name;
const points = (c: CriterionResult | undefined) =>
  !c
    ? "Not evaluated"
    : c.score === null
      ? "Unavailable"
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
  const A = useRun(aId);
  const B = useRun(bId);

  const ready = A.run && B.run && aId !== bId;
  const rows = ready ? fieldRows(A.run!, B.run!) : [];
  const changedLabels = rows.filter((r) => r.changed).map((r) => r.label);

  const criteriaKeys: string[] = [];
  if (ready)
    for (const c of [...A.run!.criteria, ...B.run!.criteria])
      if (!criteriaKeys.includes(key(c))) criteriaKeys.push(key(c));
  const find = (run: RunResponse, k: string) => run.criteria.find((c) => key(c) === k);

  const select = (label: string, value: string, set: (v: string) => void) => (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => set(e.target.value)}>
        <option value="">Choose a saved run</option>
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {optionLabel(r)}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <section className="panel comparison" aria-labelledby="comparison-title">
      <div className="result-heading">
        <h2 id="comparison-title">Compare two runs</h2>
        <button type="button" className="secondary-button" onClick={onBack}>
          Close comparison
        </button>
      </div>

      {runs.length < 2 ? (
        <p className="muted">Save at least two runs to compare them.</p>
      ) : (
        <>
          <div className="field-row">
            {select("Run A", aId, setAId)}
            {select("Run B", bId, setBId)}
          </div>
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

          {(A.loading || B.loading) && <p role="status">Loading runs…</p>}
          {A.error && (
            <p role="alert" className="error-text">
              Run A: {A.error}
            </p>
          )}
          {B.error && (
            <p role="alert" className="error-text">
              Run B: {B.error}
            </p>
          )}
          {aId && bId && aId === bId && (
            <p role="status" className="muted">
              Choose two different runs to see what changed.
            </p>
          )}
          {(!aId || !bId) && <p className="muted">Choose a run for both A and B.</p>}

          {ready && (
            <>
              <p role="status" className="change-summary">
                {changedLabels.length
                  ? `Changed between these runs: ${changedLabels.join(", ")}.`
                  : "The prompts, system instructions, rubric and settings are identical."}
              </p>

              <table className="compare-table">
                <caption>Inputs, rubric and settings</caption>
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">Run A</th>
                    <th scope="col">Run B</th>
                    <th scope="col">Difference</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.label} data-changed={r.changed}>
                      <th scope="row">{r.label}</th>
                      <td>{r.long ? <pre className="compare-text">{r.a}</pre> : r.a}</td>
                      <td>{r.long ? <pre className="compare-text">{r.b}</pre> : r.b}</td>
                      <td>
                        <Changed changed={r.changed} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <table className="compare-table">
                <caption>Criterion points</caption>
                <thead>
                  <tr>
                    <th scope="col">Criterion</th>
                    <th scope="col">Run A</th>
                    <th scope="col">Run B</th>
                    <th scope="col">B − A</th>
                  </tr>
                </thead>
                <tbody>
                  {criteriaKeys.map((k) => {
                    const ca = find(A.run!, k);
                    const cb = find(B.run!, k);
                    return (
                      <tr key={k} data-changed={points(ca) !== points(cb)}>
                        <th scope="row">{(ca ?? cb)!.name}</th>
                        <td>{points(ca)}</td>
                        <td>{points(cb)}</td>
                        <td>{diff(ca?.score, cb?.score)}</td>
                      </tr>
                    );
                  })}
                  <tr className="total-row" data-changed={A.run!.score !== B.run!.score}>
                    <th scope="row">Automated total</th>
                    <td>{total(A.run!)}</td>
                    <td>{total(B.run!)}</td>
                    <td>{diff(A.run!.score, B.run!.score)}</td>
                  </tr>
                </tbody>
              </table>
              {(A.run!.score === null || B.run!.score === null) && (
                <p className="muted">
                  A total is unavailable when any selected criterion has no valid result.
                </p>
              )}

              <table className="compare-table">
                <caption>Execution</caption>
                <thead>
                  <tr>
                    <th scope="col">Measure</th>
                    <th scope="col">Run A</th>
                    <th scope="col">Run B</th>
                    <th scope="col">B − A</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Status</th>
                    <td>{A.run!.status}</td>
                    <td>{B.run!.status}</td>
                    <td>—</td>
                  </tr>
                  <tr>
                    <th scope="row">Model used</th>
                    <td>{A.run!.model}</td>
                    <td>{B.run!.model}</td>
                    <td>—</td>
                  </tr>
                  <tr>
                    <th scope="row">Latency</th>
                    <td>{A.run!.latency_ms === null ? "Unavailable" : `${A.run!.latency_ms} ms`}</td>
                    <td>{B.run!.latency_ms === null ? "Unavailable" : `${B.run!.latency_ms} ms`}</td>
                    <td>{diff(A.run!.latency_ms, B.run!.latency_ms, 0)} ms</td>
                  </tr>
                  {(["input", "output", "total"] as const).map((part) => {
                    const ta = tokens(A.run!)[part];
                    const tb = tokens(B.run!)[part];
                    return (
                      <tr key={part}>
                        <th scope="row">{part[0].toUpperCase() + part.slice(1)} tokens</th>
                        <td>{ta ?? "Not reported"}</td>
                        <td>{tb ?? "Not reported"}</td>
                        <td>{diff(ta, tb, 0)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <h3>Responses</h3>
              <p className="muted">
                {A.run!.response === B.run!.response
                  ? "The two responses are identical."
                  : "The responses differ."}
              </p>
              <div className="field-row">
                <div className="response-box">
                  <h4>Run A</h4>
                  <p>{A.run!.response || "No response was saved."}</p>
                </div>
                <div className="response-box">
                  <h4>Run B</h4>
                  <p>{B.run!.response || "No response was saved."}</p>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
