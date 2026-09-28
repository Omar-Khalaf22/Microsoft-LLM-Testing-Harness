import type { RunResponse } from "./api";

function RunResults({ run }: { run: RunResponse | null }) {
  const usage = run?.metadata.usage;

  return (
    <section className="panel result-panel" aria-label="Selected run result">
      {!run ? (
        <div className="empty-state">
          <div className="pulse" aria-hidden="true" />
          <p>Run a test or open a saved run to see its evaluation results.</p>
        </div>
      ) : (
        <div className="result-body">
          <div className="result-summary">
            <div className="score-ring" aria-label={`Score ${run.score} out of 100`}>
              <strong>{run.score}</strong>
              <small>/100</small>
            </div>
            <div className="result-summary-text">
              <span className={`badge ${run.passed ? "" : "fail"}`}>
                {run.passed ? "PASS" : "REVIEW"}
              </span>
              <h3>{run.metadata.test_name || "Untitled test"}</h3>
              <p>
                {run.model} · {run.latency_ms} ms · {run.provider} · status: {run.status}
              </p>
            </div>
          </div>

          <div className="response-box">
            <h4>Model response</h4>
            <p>{run.response || "No response was returned."}</p>
          </div>

          <div className="criteria-list">
            <h4>Individual evaluation results</h4>
            {run.criteria.map((criterion) => (
              <div className="criterion" key={criterion.name}>
                <span className={`mark ${criterion.passed ? "" : "fail"}`} aria-hidden="true">
                  {criterion.passed ? "✓" : "×"}
                </span>
                <div>
                  <strong>{criterion.name}</strong>
                  <p>{criterion.detail}</p>
                </div>
                <span className="points">{criterion.score}</span>
              </div>
            ))}
          </div>

          <dl className="run-metrics">
            <div><dt>Run</dt><dd>{run.id.slice(0, 8)}</dd></div>
            {run.metadata.test_version && (
              <div><dt>Version</dt><dd>{run.metadata.test_version}</dd></div>
            )}
            {usage?.input_tokens !== undefined && (
              <div><dt>Input tokens</dt><dd>{usage.input_tokens}</dd></div>
            )}
            {usage?.output_tokens !== undefined && (
              <div><dt>Output tokens</dt><dd>{usage.output_tokens}</dd></div>
            )}
            <div><dt>Saved</dt><dd>{new Date(run.created_at).toLocaleString()}</dd></div>
          </dl>

          <details className="json-details">
            <summary>Structured JSON result</summary>
            <pre>{JSON.stringify(run, null, 2)}</pre>
          </details>
        </div>
      )}
    </section>
  );
}

export default RunResults;
