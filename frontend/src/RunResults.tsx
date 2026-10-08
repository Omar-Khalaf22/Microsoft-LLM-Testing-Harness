import type { RunResponse } from "./api";

function availableNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function RunResults({ run }: { run: RunResponse | null }) {
  const usage = run?.metadata.usage;
  const inputTokens = availableNumber(usage?.input_tokens);
  const outputTokens = availableNumber(usage?.output_tokens);
  const suppliedTotal = availableNumber(usage && "total_tokens" in usage ? usage.total_tokens : undefined);
  const totalTokens = suppliedTotal ?? (
    inputTokens !== undefined && outputTokens !== undefined ? inputTokens + outputTokens : undefined
  );
  const latency = availableNumber(run?.latency_ms);
  const latencyDisplay = latency === undefined ? "\u2014" : latency < 1000
    ? `${latency} ms` : `${(Math.round(latency / 10) / 100).toFixed(2)} s`;
  const provider = run?.provider === "openai_compatible" ? "OpenAI" : run?.provider;

  return (
    <section className="panel result-panel" aria-label="Selected run result">
      <div className="section-title">
        <span className="section-number">02</span>
        <h2>{run ? "Saved result" : "Latest result"}</h2>
      </div>
      {!run ? (
        <div className="empty-state">
          <div className="pulse" aria-hidden="true" />
          <p>Run a test or open a saved run to see its results.</p>
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
            </div>
          </div>

          <section className="execution-metrics" aria-labelledby="run-metrics-title">
            <h4 id="run-metrics-title">Run Metrics</h4>
            <dl className="execution-metrics-grid">
              <div><dt>Model</dt><dd>{run.model?.trim() || "\u2014"}</dd></div>
              <div><dt>Provider</dt><dd>{provider?.trim() || "\u2014"}</dd></div>
              <div><dt>Latency</dt><dd>{latencyDisplay}</dd></div>
              <div><dt>Input Tokens</dt><dd>{inputTokens ?? "\u2014"}</dd></div>
              <div><dt>Output Tokens</dt><dd>{outputTokens ?? "\u2014"}</dd></div>
              <div><dt>Total Tokens</dt><dd>{totalTokens ?? "\u2014"}</dd></div>
            </dl>
          </section>

          <div className="response-box">
            <h4>Model response</h4>
            <p>{run.response || "No response was saved."}</p>
          </div>

          <div className="criteria-list">
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
