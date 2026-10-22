import type { RunResponse } from "./api";
const available = (x: unknown): number | undefined =>
  typeof x === "number" && Number.isFinite(x) && x >= 0 ? x : undefined;
export default function RunResults({ run }: { run: RunResponse | null }) {
  if (!run)
    return (
      <section className="panel result-panel">
        <h2>Saved result</h2>
        <p className="muted">
          Run a test or open a saved run to inspect its evidence.
        </p>
      </section>
    );
  const usage = run.metadata.usage;
  const input = available(usage?.input_tokens);
  const output = available(usage?.output_tokens);
  const total =
    available(usage?.total_tokens) ??
    (input !== undefined && output !== undefined ? input + output : undefined);
  return (
    <section className="panel result-panel" aria-label="Selected run result">
      <div className="result-heading">
        <div>
          <h2>{run.metadata.test_name || "Saved result"}</h2>
          <p className="muted">
            Version {run.metadata.test_version ?? "unknown"} ·{" "}
            {new Date(run.created_at).toLocaleString()}
          </p>
        </div>
        <span className="execution-status">Execution: {run.status}</span>
      </div>
      <p className="score-summary">
        Automated score{" "}
        <strong>
          {run.score === null
            ? "Unavailable"
            : `${run.score.toFixed(2)} / 100.00`}
        </strong>
      </p>
      {run.error && (
        <p role="alert" className="error-text">
          {run.error.message}
        </p>
      )}
      {run.score === null && (
        <p className="muted">
          A total is available only when all selected criteria have valid
          results.
        </p>
      )}
      <dl className="execution-metrics-grid">
        <div>
          <dt>Model</dt>
          <dd>{run.model}</dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{run.provider === "local_demo" ? "Local demo" : run.provider}</dd>
        </div>
        <div>
          <dt>Latency</dt>
          <dd>{run.latency_ms} ms</dd>
        </div>
        <div>
          <dt>Input tokens</dt>
          <dd>{input ?? "Not reported"}</dd>
        </div>
        <div>
          <dt>Output tokens</dt>
          <dd>{output ?? "Not reported"}</dd>
        </div>
        <div>
          <dt>Total tokens</dt>
          <dd>{total ?? "Not reported"}</dd>
        </div>
      </dl>
      <div className="response-box">
        <h3>Model response</h3>
        <p>{run.response || "No response was saved."}</p>
      </div>
      <h3>Criterion evidence</h3>
      <div className="criteria-list">
        {run.criteria.map((c, i) => (
          <div
            className="criterion evidence-row"
            key={c.criterion_id ?? `${c.name}-${i}`}
          >
            <div>
              <strong>{c.name}</strong>
              <p>{c.detail}</p>
              {c.normalized_score !== null &&
                c.normalized_score !== undefined && (
                  <p>Completion value: {c.normalized_score.toFixed(4)}</p>
                )}
              <p>
                Evaluation:{" "}
                {c.status === "error" ? "Incomplete" : (c.status ?? "Recorded")}
              </p>
            </div>
            <span className="points">
              {c.score === null ? "Unavailable" : c.score.toFixed(2)}
              {c.maximum_points !== null && c.maximum_points !== undefined
                ? ` / ${c.maximum_points.toFixed(2)}`
                : " points (maximum unknown)"}
            </span>
          </div>
        ))}
      </div>
      <details className="json-details">
        <summary>Saved configuration</summary>
        <p>
          System instructions, approved criteria, and original suggestions are
          retained with this run.
        </p>
        <pre>
          {JSON.stringify(
            {
              objective: run.metadata.objective,
              base_system_prompt: run.metadata.base_system_prompt,
              custom_system_prompt: run.metadata.custom_system_prompt,
              resolved_system_prompt: run.metadata.resolved_system_prompt,
              criteria: run.metadata.criteria,
              scoring_weights: run.metadata.scoring_weights,
              configuration_state: run.metadata.configuration_state,
              generated_configuration: run.metadata.generated_configuration,
            },
            null,
            2,
          )}
        </pre>
      </details>
      <details className="json-details">
        <summary>Complete run JSON</summary>
        <pre>{JSON.stringify(run, null, 2)}</pre>
      </details>
    </section>
  );
}
