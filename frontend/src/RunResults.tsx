import type { RunResponse } from "./api";

function RunCard({ run }: { run: RunResponse }) {
  const usage = run.metadata.usage;

  return (
    <article className="run-card">
      <header className="run-card-header">
        <div>
          <h3>{run.prompt}</h3>
          <p className="run-card-subtitle">
            {run.model} · {run.provider}
          </p>
        </div>
        <span className="status-badge" data-run-status={run.status}>
          {run.status}
        </span>
      </header>

      <section className="run-card-section">
        <h4>Response</h4>
        <pre className="run-response">{run.response}</pre>
      </section>

      <section className="run-card-section">
        <h4>Evaluation</h4>
        <p>
          Score: <strong data-passed={run.passed}>{run.score}</strong> (
          {run.passed ? "passed" : "failed"})
        </p>
        {run.criteria.length > 0 && (
          <ul className="evaluation-list">
            {run.criteria.map((criterion) => (
              <li key={criterion.name}>
                <span>{criterion.name}</span>
                <span data-passed={criterion.passed}>
                  {criterion.score} ({criterion.passed ? "passed" : "failed"}) — {criterion.detail}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="run-card-section">
        <h4>Run metrics</h4>
        <dl className="metrics-grid">
          <dt>Latency</dt>
          <dd>{run.latency_ms} ms</dd>
          {usage?.input_tokens !== undefined && (
            <>
              <dt>Input tokens</dt>
              <dd>{usage.input_tokens}</dd>
            </>
          )}
          {usage?.output_tokens !== undefined && (
            <>
              <dt>Output tokens</dt>
              <dd>{usage.output_tokens}</dd>
            </>
          )}
          <dt>Created</dt>
          <dd>{new Date(run.created_at).toLocaleString()}</dd>
        </dl>
      </section>
    </article>
  );
}

function RunResults({ runs }: { runs: RunResponse[] }) {
  return (
    <section className="run-results">
      <div className="run-results-header">
        <h2>Test run results</h2>
      </div>

      {runs.length === 0 ? (
        <p className="muted">No runs yet — submit a prompt above to test a model.</p>
      ) : (
        <div className="run-card-list">
          {runs.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}
    </section>
  );
}

export default RunResults;
